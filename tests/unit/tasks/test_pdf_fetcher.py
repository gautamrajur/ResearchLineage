"""
Unit tests for PDF fetcher (pytest).

Tests helpers (paper_id_to_filename, build_blob_metadata, _validate_pdf),
resolve_pdf_url fallback chain, fetch_pdf_bytes, fetch_and_upload, fetch_batch.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.tasks.pdf_fetcher import (
    ARXIV_PDF_BASE,
    paper_id_to_filename,
    build_blob_metadata,
    PDFFetcher,
)


def _run(coro):
    return asyncio.run(coro)


def test_paper_id_to_filename():
    """paper_id_to_filename: returns paper_id with .pdf suffix."""
    assert paper_id_to_filename("abc123") == "abc123.pdf"
    assert paper_id_to_filename("204e3073870fae3d05bcbc2f6a8e263d9b72e776") == "204e3073870fae3d05bcbc2f6a8e263d9b72e776.pdf"
    assert paper_id_to_filename("") == ".pdf"


def test_filename_special_inputs():
    """paper_id_to_filename: single char, long, unicode, special chars."""
    # Single character
    assert paper_id_to_filename("a") == "a.pdf"
    # Very long (Semantic Scholar IDs are 40 chars; allow longer)
    long_id = "a" * 200
    assert paper_id_to_filename(long_id) == long_id + ".pdf"
    # Unicode (no sanitization in impl; document behavior)
    assert paper_id_to_filename("日本") == "日本.pdf"
    # Special chars (spaces, hyphens) – impl does not strip
    assert paper_id_to_filename("id-with-dashes") == "id-with-dashes.pdf"
    assert paper_id_to_filename("id with spaces") == "id with spaces.pdf"
    # Numeric-looking string
    assert paper_id_to_filename("123") == "123.pdf"


def test_build_blob_metadata():
    """build_blob_metadata: arxiv_id, file_name, published_year, published_month."""
    paper = {
        "title": "Attention Is All You Need",
        "year": 2017,
        "publicationDate": "2017-06-12",
        "externalIds": {"ArXiv": "1706.03762"},
    }
    out = build_blob_metadata(paper)
    assert out["arxiv_id"] == "1706.03762"
    assert out["file_name"] == "Attention Is All You Need"
    assert out["published_year"] == "2017"
    assert out["published_month"] == "06"

    empty = build_blob_metadata({})
    assert empty["arxiv_id"] == ""
    assert empty["file_name"] == ""
    assert empty["published_year"] == ""
    assert empty["published_month"] == ""


def test_blob_metadata_variants():
    """build_blob_metadata: missing/zero/None fields and key set."""
    # year is 0 (falsy) -> published_year ""
    out = build_blob_metadata({"year": 0, "title": "T", "publicationDate": "2020-01-15"})
    assert out["published_year"] == ""
    assert out["published_month"] == "01"

    # year is None
    out = build_blob_metadata({"year": None, "title": "T"})
    assert out["published_year"] == ""

    # publicationDate missing -> month ""
    out = build_blob_metadata({"title": "T", "year": 2020})
    assert out["published_month"] == ""
    assert out["published_year"] == "2020"

    # publicationDate single segment (e.g. "2017") -> no month
    out = build_blob_metadata({"title": "T", "publicationDate": "2017"})
    assert out["published_month"] == ""

    # title missing / None (paper.get("title", "") returns "" when missing, None when key exists with value None)
    out = build_blob_metadata({"year": 2020})
    assert out["file_name"] == ""
    out = build_blob_metadata({"title": None, "year": 2020})
    assert out["file_name"] in (None, "")  # impl may return None when title key exists with value None

    # externalIds None -> arxiv_id ""
    out = build_blob_metadata({"externalIds": None, "title": "T"})
    assert out["arxiv_id"] == ""

    # Returned dict has exactly four keys
    out = build_blob_metadata({"title": "T", "year": 1})
    assert set(out.keys()) == {"arxiv_id", "file_name", "published_year", "published_month"}
    assert len(out) == 4


def test_validate_pdf():
    """_validate_pdf: requires at least 1024 bytes and %PDF- header."""
    valid = b"%PDF-1.4\n" + b"x" * 1020
    assert PDFFetcher._validate_pdf(valid) is True

    too_small = b"%PDF-1.4\n" + b"x" * 100
    assert PDFFetcher._validate_pdf(too_small) is False

    not_pdf = b"<!DOCTYPE html>" + b"x" * 1100
    assert PDFFetcher._validate_pdf(not_pdf) is False

    exact_1024 = b"%PDF-" + b"a" * 1019
    assert PDFFetcher._validate_pdf(exact_1024) is True


def test_validate_pdf_boundary():
    """_validate_pdf: length boundary, empty, wrong magic bytes."""
    # Boundary: 1023 bytes with %PDF- -> False
    just_under = b"%PDF-" + b"x" * 1018
    assert len(just_under) == 1023
    assert PDFFetcher._validate_pdf(just_under) is False

    # Boundary: 1025 bytes with %PDF- -> True
    just_over = b"%PDF-" + b"x" * 1020
    assert len(just_over) == 1025
    assert PDFFetcher._validate_pdf(just_over) is True

    # Empty bytes
    assert PDFFetcher._validate_pdf(b"") is False

    # Exactly 5 bytes "%PDF-" -> too short
    assert PDFFetcher._validate_pdf(b"%PDF-") is False

    # 1024 bytes but wrong magic (5th byte not hyphen)
    wrong_magic = b"%PDFx" + b"y" * 1019
    assert len(wrong_magic) == 1024
    assert PDFFetcher._validate_pdf(wrong_magic) is False

    # 1024 bytes but prefix not %PDF- (e.g. space before)
    no_magic = b" XXXXX" + b"y" * 1018
    assert len(no_magic) == 1024
    assert PDFFetcher._validate_pdf(no_magic) is False

    # Valid minimal: exactly 1024 bytes, correct header
    minimal = b"%PDF-" + b"z" * 1019
    assert len(minimal) == 1024
    assert PDFFetcher._validate_pdf(minimal) is True


# ─── resolve_pdf_url (ArXiv → S2 → Unpaywall chain) ─────────────────────

@pytest.fixture
def pdf_fetcher():
    gcs = MagicMock(spec=["exists", "upload", "exists_batch", "base_uri"])
    gcs.base_uri = "gs://bucket/"
    return PDFFetcher(gcs_client=gcs, max_retries=2, retry_delay=0.01)


def test_resolve_pdf_url_arxiv_only(pdf_fetcher):
    """ArXiv ID present: returns deterministic URL, no HTTP call."""
    paper = {"paperId": "p1", "externalIds": {"ArXiv": "1706.03762"}}
    async def _():
        async with httpx.AsyncClient() as client:
            out = await pdf_fetcher.resolve_pdf_url(paper, client)
        assert out is not None
        url, source = out
        assert source == "arxiv"
        assert url == f"{ARXIV_PDF_BASE}/1706.03762.pdf"
    _run(_())


def test_resolve_pdf_url_no_paper_id_returns_none(pdf_fetcher):
    """No paperId: after ArXiv miss, returns None without calling S2."""
    paper = {"title": "No ID", "externalIds": {}}
    async def _():
        async with httpx.AsyncClient() as client:
            out = await pdf_fetcher.resolve_pdf_url(paper, client)
        assert out is None
    _run(_())


def test_resolve_pdf_url_s2_fallback(pdf_fetcher):
    """No ArXiv; S2 openAccessPdf returns URL."""
    paper = {"paperId": "s2id123", "title": "T", "externalIds": {}}
    def _handler(request: httpx.Request) -> httpx.Response:
        if "paper/" in str(request.url) and "openAccessPdf" in str(request.url.query or ""):
            return httpx.Response(200, json={"openAccessPdf": {"url": "https://pdf.example.com/paper.pdf"}})
        return httpx.Response(404)
    transport = httpx.MockTransport(_handler)
    async def _():
        async with httpx.AsyncClient(transport=transport) as client:
            out = await pdf_fetcher.resolve_pdf_url(paper, client)
        assert out is not None
        url, source = out
        assert source == "semantic_scholar"
        assert "pdf.example.com" in url
    _run(_())


def test_resolve_pdf_url_unpaywall_fallback(pdf_fetcher):
    """No ArXiv, no S2; Unpaywall returns url_for_pdf."""
    paper = {"paperId": "p1", "title": "T", "externalIds": {"DOI": "10.1234/foo"}}
    def _handler(request: httpx.Request) -> httpx.Response:
        if "unpaywall" in str(request.url):
            return httpx.Response(200, json={"best_oa_location": {"url_for_pdf": "https://oa.example.com/10.1234.pdf"}})
        return httpx.Response(404)
    transport = httpx.MockTransport(_handler)
    async def _():
        async with httpx.AsyncClient(transport=transport) as client:
            out = await pdf_fetcher.resolve_pdf_url(paper, client)
        assert out is not None
        url, source = out
        assert source == "unpaywall"
        assert "oa.example.com" in url
    _run(_())


def test_resolve_pdf_url_no_pdf_from_any_source(pdf_fetcher):
    """No ArXiv, S2 and Unpaywall return no PDF."""
    paper = {"paperId": "p1", "title": "T", "externalIds": {}}
    def _handler(request: httpx.Request) -> httpx.Response:
        if "paper/" in str(request.url):
            return httpx.Response(200, json={})
        return httpx.Response(404)
    transport = httpx.MockTransport(_handler)
    async def _():
        async with httpx.AsyncClient(transport=transport) as client:
            out = await pdf_fetcher.resolve_pdf_url(paper, client)
        assert out is None
    _run(_())


# ─── fetch_pdf_bytes ───────────────────────────────────────────────────

def test_fetch_pdf_bytes_success(pdf_fetcher):
    """200 + valid PDF content returns bytes."""
    valid_pdf = b"%PDF-1.4\n" + b"x" * 1020
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=valid_pdf)
    transport = httpx.MockTransport(_handler)
    async def _():
        async with httpx.AsyncClient(transport=transport) as client:
            out = await pdf_fetcher.fetch_pdf_bytes("https://example.com/doc.pdf", client)
        assert out == valid_pdf
    _run(_())


def test_fetch_pdf_bytes_non_200_returns_none(pdf_fetcher):
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)
    transport = httpx.MockTransport(_handler)
    async def _():
        async with httpx.AsyncClient(transport=transport) as client:
            out = await pdf_fetcher.fetch_pdf_bytes("https://example.com/missing.pdf", client)
        assert out is None
    _run(_())


def test_fetch_pdf_bytes_invalid_content_returns_none(pdf_fetcher):
    """Response 200 but content too short or not PDF."""
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"%PDF-" + b"x" * 100)
    transport = httpx.MockTransport(_handler)
    async def _():
        async with httpx.AsyncClient(transport=transport) as client:
            out = await pdf_fetcher.fetch_pdf_bytes("https://example.com/fake.pdf", client)
        assert out is None
    _run(_())


# ─── fetch_and_upload ──────────────────────────────────────────────────

def test_fetch_and_upload_no_paper_id(pdf_fetcher):
    """Paper with no paperId returns error result."""
    async def _():
        r = await pdf_fetcher.fetch_and_upload({"title": "No ID"})
        assert r.status == "error"
        assert r.paper_id == "missing"
        assert "paper" in r.error.lower()
        assert "paperid" in r.error.lower().replace(" ", "")
    _run(_())


def test_fetch_and_upload_exists_in_gcs(pdf_fetcher):
    """If GCS already has file, returns status=exists."""
    pdf_fetcher.gcs.exists = MagicMock(return_value=True)
    async def _():
        r = await pdf_fetcher.fetch_and_upload({
            "paperId": "abc",
            "title": "T",
            "externalIds": {},
        })
        assert r.status == "exists"
        assert r.gcs_uri
    _run(_())


def test_fetch_and_upload_no_pdf_resolved(pdf_fetcher):
    """resolve_pdf_url returns None -> status no_pdf."""
    pdf_fetcher.gcs.exists = MagicMock(return_value=False)
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={}))
    async def _():
        async with httpx.AsyncClient(transport=transport) as client:
            r = await pdf_fetcher.fetch_and_upload(
                {"paperId": "p1", "title": "T", "externalIds": {}},
                http_client=client,
            )
        assert r.status == "no_pdf"
    _run(_())


def test_fetch_and_upload_download_failed_then_no_pdf(pdf_fetcher):
    """S2 returns URL but fetch_pdf_bytes fails -> download_failed."""
    pdf_fetcher.gcs.exists = MagicMock(return_value=False)
    call_count = [0]
    def _handler(request: httpx.Request) -> httpx.Response:
        call_count[0] += 1
        if "paper/" in str(request.url):
            return httpx.Response(200, json={"openAccessPdf": {"url": "https://example.com/paper.pdf"}})
        return httpx.Response(404)
    transport = httpx.MockTransport(_handler)
    async def _():
        async with httpx.AsyncClient(transport=transport) as client:
            r = await pdf_fetcher.fetch_and_upload(
                {"paperId": "p1", "title": "T", "externalIds": {}},
                http_client=client,
            )
        assert r.status == "download_failed"
    _run(_())


def test_fetch_and_upload_full_flow_uploaded(pdf_fetcher):
    """Resolve (ArXiv) -> download valid PDF -> upload to GCS -> uploaded."""
    pdf_fetcher.gcs.exists = MagicMock(return_value=False)
    pdf_fetcher.gcs.upload = MagicMock(return_value="gs://bucket/abc.pdf")
    valid_pdf = b"%PDF-1.4\n" + b"y" * 1020
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=valid_pdf)
    transport = httpx.MockTransport(_handler)
    async def _():
        async with httpx.AsyncClient(transport=transport) as client:
            r = await pdf_fetcher.fetch_and_upload(
                {"paperId": "abc", "title": "T", "externalIds": {"ArXiv": "1706.03762"}},
                http_client=client,
            )
        assert r.status == "uploaded"
        assert r.source == "arxiv"
        assert r.size_bytes == len(valid_pdf)
        assert r.gcs_uri == "gs://bucket/abc.pdf"
    _run(_())


# ─── fetch_batch ───────────────────────────────────────────────────────

def test_fetch_batch_empty_list(pdf_fetcher):
    async def _():
        batch = await pdf_fetcher.fetch_batch([])
        assert batch.total == 0
        assert batch.uploaded == 0
    _run(_())


def test_fetch_batch_all_already_in_gcs(pdf_fetcher):
    """exists_batch returns all filenames -> no fetch, only exists results."""
    pdf_fetcher.gcs.exists_batch = MagicMock(return_value={"p1.pdf", "p2.pdf"})
    async def _():
        batch = await pdf_fetcher.fetch_batch([
            {"paperId": "p1", "title": "A"},
            {"paperId": "p2", "title": "B"},
        ])
        assert batch.already_in_gcs == 2
        assert batch.uploaded == 0
        assert len(batch.results) == 2
        assert all(r.status == "exists" for r in batch.results)
    _run(_())


def test_fetch_batch_mixed_concurrency(pdf_fetcher):
    """Batch with concurrency: resolve -> download -> upload path; GCS upload called."""
    pdf_fetcher.gcs.exists_batch = MagicMock(return_value=set())
    pdf_fetcher.gcs.upload = MagicMock(return_value="gs://bucket/x.pdf")
    valid_pdf = b"%PDF-1.4\n" + b"z" * 1020
    async def _():
        # Stub resolve and fetch so batch orchestration (semaphore, gather, upload) runs
        async def _resolve(paper, client):
            return ("https://arxiv.org/pdf/1234.5678.pdf", "arxiv")
        async def _fetch(url, client):
            return valid_pdf
        pdf_fetcher.resolve_pdf_url = _resolve
        pdf_fetcher.fetch_pdf_bytes = _fetch
        papers = [
            {"paperId": "a1", "title": "A", "externalIds": {"ArXiv": "1234.5678"}},
            {"paperId": "a2", "title": "B", "externalIds": {"ArXiv": "1234.5679"}},
        ]
        batch = await pdf_fetcher.fetch_batch(papers)
        assert batch.uploaded == 2
        assert len(batch.results) == 2
        assert pdf_fetcher.gcs.upload.call_count == 2
    _run(_())
