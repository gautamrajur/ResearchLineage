"""PDF fetching task — resolve URLs, download, and upload to GCS.

Designed for standalone use and for future integration into the data
acquisition pipeline where papers are processed as they arrive.

Fallback chain for PDF URL resolution:
  1. ArXiv ID      → deterministic URL, zero API cost
  2. Semantic Scholar openAccessPdf → one lightweight API call
  3. Unpaywall DOI → free open-access lookup by DOI
"""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set

import httpx

from src.storage.gcs_client import GCSClient
from src.utils.config import settings
from src.utils.id_mapper import IDMapper

logger = logging.getLogger(__name__)

ARXIV_PDF_BASE = "https://arxiv.org/pdf"
S2_API_BASE = settings.semantic_scholar_base_url
UNPAYWALL_BASE = "https://api.unpaywall.org/v2"
UNPAYWALL_EMAIL = "research-lineage@example.com"


@dataclass
class FetchResult:
    """Outcome of a single paper PDF fetch attempt."""

    paper_id: str
    title: str
    status: str  # "uploaded", "exists", "no_pdf", "download_failed", "error"
    gcs_uri: str = ""
    source: str = ""  # "arxiv", "semantic_scholar", "unpaywall"
    size_bytes: int = 0
    error: str = ""
    fetch_url: str = ""  # URL that was tried (for failure recording / retry)
    response_code: int = 0  # HTTP status when applicable (e.g. 403, 404)


@dataclass
class BatchResult:
    """Aggregated results from a batch fetch."""

    uploaded: int = 0
    already_in_gcs: int = 0
    no_pdf_found: int = 0
    download_failed: int = 0
    errors: int = 0
    results: List[FetchResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)


def paper_id_to_filename(paper_id: str) -> str:
    return f"{paper_id}.pdf"


def build_blob_metadata(paper: Dict[str, Any]) -> Dict[str, str]:
    """Extract GCS blob metadata from paper data."""
    arxiv_id = IDMapper.extract_arxiv_id(paper) or ""
    pub_date = paper.get("publicationDate", "") or ""
    year = str(paper.get("year", "")) if paper.get("year") else ""
    month = pub_date.split("-")[1] if pub_date and len(pub_date.split("-")) >= 2 else ""

    return {
        "arxiv_id": arxiv_id,
        "file_name": paper.get("title", ""),
        "published_year": year,
        "published_month": month,
    }


class PDFFetcher:
    """
    Fetches PDFs for academic papers and uploads them to GCS.

    Can be used:
      - In batch mode: fetch_batch(papers) for a list of papers
      - Per-paper: fetch_and_upload(paper) for pipeline integration
    """

    def __init__(
        self,
        gcs_client: GCSClient,
        max_retries: int = 3,
        retry_delay: float = 30,
        download_timeout: float = 120.0,
        concurrency: int = 3,
    ):
        self.gcs = gcs_client
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.download_timeout = download_timeout
        self.concurrency = concurrency

        self._api_headers: Dict[str, str] = {}
        if settings.semantic_scholar_api_key:
            self._api_headers["x-api-key"] = settings.semantic_scholar_api_key

    # ── URL Resolution (3-source fallback chain) ─────────────────────

    async def resolve_pdf_url(
        self,
        paper: Dict[str, Any],
        http_client: httpx.AsyncClient,
    ) -> Optional[tuple[str, str]]:
        """
        Resolve a downloadable PDF URL for a paper.

        Returns:
            (url, source) tuple, or None if no PDF found.
            source is one of: "arxiv", "semantic_scholar", "unpaywall"
        """
        paper_id = paper.get("paperId", "unknown")
        url = self._try_arxiv(paper)
        if url:
            logger.info("paper_id=%s resolve arxiv=found url=%s", paper_id, url[:80] + "..." if len(url) > 80 else url)
            return url, "arxiv"
        logger.info("paper_id=%s resolve arxiv=no_id", paper_id)

        if not paper_id or paper_id == "unknown":
            logger.info("paper_id=%s resolve no_paper_id", paper_id)
            return None

        url = await self._try_semantic_scholar(paper_id, http_client)
        if url:
            logger.info("paper_id=%s resolve semantic_scholar=found", paper_id)
            return url, "semantic_scholar"
        logger.info("paper_id=%s resolve semantic_scholar=not_found", paper_id)

        doi = IDMapper.extract_doi(paper)
        if doi:
            url = await self._try_unpaywall(doi, http_client)
            if url:
                logger.info("paper_id=%s resolve unpaywall=found", paper_id)
                return url, "unpaywall"
            logger.info("paper_id=%s resolve unpaywall=not_found doi=%s", paper_id, doi[:50] if doi else "")
        else:
            logger.info("paper_id=%s resolve unpaywall=no_doi", paper_id)

        logger.info("paper_id=%s resolve no_pdf_from_any_source", paper_id)
        return None

    def _try_arxiv(self, paper: Dict[str, Any]) -> Optional[str]:
        """Attempt 1: Construct URL from ArXiv ID (no API call)."""
        arxiv_id = IDMapper.extract_arxiv_id(paper)
        if arxiv_id:
            return f"{ARXIV_PDF_BASE}/{arxiv_id}.pdf"
        return None

    async def _try_semantic_scholar(
        self, paper_id: str, client: httpx.AsyncClient
    ) -> Optional[str]:
        """Attempt 2: Query Semantic Scholar openAccessPdf field with retries."""
        for attempt in range(self.max_retries):
            try:
                resp = await client.get(
                    f"{S2_API_BASE}/paper/{paper_id}",
                    params={"fields": "openAccessPdf"},
                    headers=self._api_headers,
                    timeout=15,
                )
                if resp.status_code == 200:
                    oa = resp.json().get("openAccessPdf")
                    if oa and oa.get("url"):
                        return oa["url"]
                    return None
                if resp.status_code == 429:
                    logger.debug(f"S2 rate limited for {paper_id}, retry {attempt + 1}/{self.max_retries}")
                    await asyncio.sleep(self.retry_delay)
                    continue
                return None
            except Exception as e:
                logger.debug(f"S2 openAccessPdf error for {paper_id}: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay)
        return None

    async def _try_unpaywall(
        self, doi: str, client: httpx.AsyncClient
    ) -> Optional[str]:
        """Attempt 3: Query Unpaywall for open-access PDF by DOI."""
        for attempt in range(self.max_retries):
            try:
                resp = await client.get(
                    f"{UNPAYWALL_BASE}/{doi}",
                    params={"email": UNPAYWALL_EMAIL},
                    timeout=15,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    best = data.get("best_oa_location") or {}
                    pdf_url = best.get("url_for_pdf")
                    if pdf_url:
                        return pdf_url
                    return None
                if resp.status_code == 429:
                    await asyncio.sleep(self.retry_delay)
                    continue
                return None
            except Exception as e:
                logger.debug(f"Unpaywall error for DOI {doi}: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay)
        return None

    # ── PDF download & validation ────────────────────────────────────

    async def fetch_pdf_bytes(
        self, url: str, client: httpx.AsyncClient
    ) -> Optional[bytes]:
        """Download PDF bytes from a URL with validation."""
        for attempt in range(self.max_retries):
            try:
                resp = await client.get(
                    url, follow_redirects=True, timeout=self.download_timeout
                )
                if resp.status_code == 429:
                    await asyncio.sleep(self.retry_delay)
                    continue
                if resp.status_code != 200:
                    logger.info(
                        "pdf_download_failed url=%s status_code=%s",
                        url[:80] + "..." if len(url) > 80 else url,
                        resp.status_code,
                    )
                    return None

                content = resp.content
                if not self._validate_pdf(content):
                    logger.info(
                        "pdf_download_failed url=%s reason=invalid_content size=%d",
                        url[:80] + "..." if len(url) > 80 else url,
                        len(content),
                    )
                    return None
                return content
            except Exception as e:
                logger.debug(f"PDF download error (attempt {attempt + 1}): {e}")
                if attempt == self.max_retries - 1:
                    logger.info(
                        "pdf_download_failed url=%s reason=exception error=%s",
                        url[:80] + "..." if len(url) > 80 else url,
                        str(e),
                    )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay)
        return None

    @staticmethod
    def _validate_pdf(content: bytes) -> bool:
        """Check that content looks like a real PDF."""
        if len(content) < 1024:
            return False
        return content[:5] == b"%PDF-"

    # ── Single-paper fetch + upload ──────────────────────────────────

    async def fetch_and_upload(
        self,
        paper: Dict[str, Any],
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> FetchResult:
        """
        Resolve, download, and upload a PDF for a single paper.

        This is the primary interface for pipeline integration.
        When data_acquisition fetches a paper, it can fire this
        off in parallel immediately.

        Args:
            paper: Paper metadata dict (must have paperId, title, externalIds)
            http_client: Reusable httpx client (created if not provided)
        """
        pid = paper.get("paperId")
        title = paper.get("title", "untitled")

        if not pid:
            return FetchResult(
                paper_id="missing", title=title, status="error",
                error="Paper has no paperId",
            )

        filename = paper_id_to_filename(pid)

        if await asyncio.to_thread(self.gcs.exists, filename):
            return FetchResult(
                paper_id=pid, title=title, status="exists",
                gcs_uri=f"{self.gcs.base_uri}{filename}",
            )

        owns_client = http_client is None
        if owns_client:
            http_client = httpx.AsyncClient()

        try:
            resolved = await self.resolve_pdf_url(paper, http_client)
            if not resolved:
                return FetchResult(paper_id=pid, title=title, status="no_pdf")

            url, source = resolved
            content = await self.fetch_pdf_bytes(url, http_client)
            if content is None:
                return FetchResult(
                    paper_id=pid, title=title, status="download_failed",
                    source=source, error=f"Failed to download from {url[:80]}",
                    fetch_url=url,
                )

            metadata = build_blob_metadata(paper)
            gcs_uri = await asyncio.to_thread(
                self.gcs.upload, filename, content, "application/pdf", metadata
            )

            return FetchResult(
                paper_id=pid, title=title, status="uploaded",
                gcs_uri=gcs_uri, source=source, size_bytes=len(content),
            )
        except Exception as e:
            return FetchResult(
                paper_id=pid, title=title, status="error", error=str(e),
            )
        finally:
            if owns_client:
                await http_client.aclose()

    async def fetch_from_url_and_upload(
        self,
        paper_id: str,
        title: str,
        fetch_url: str,
        paper_metadata: Optional[Dict[str, Any]] = None,
    ) -> FetchResult:
        """
        Fetch PDF from a known URL and upload to GCS.

        Used by the retry-failed-PDFs flow where URL and timeout come from the
        fetch_pdf_failures table. Uses self.download_timeout for the request.
        """
        paper_metadata = paper_metadata or {"paperId": paper_id, "title": title}
        filename = paper_id_to_filename(paper_id)
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    fetch_url,
                    follow_redirects=True,
                    timeout=self.download_timeout,
                )
            if resp.status_code == 429:
                return FetchResult(
                    paper_id=paper_id,
                    title=title,
                    status="download_failed",
                    error="429 Too Many Requests",
                    fetch_url=fetch_url,
                    response_code=429,
                )
            if resp.status_code != 200:
                return FetchResult(
                    paper_id=paper_id,
                    title=title,
                    status="download_failed",
                    error=f"HTTP {resp.status_code}",
                    fetch_url=fetch_url,
                    response_code=resp.status_code,
                )
            content = resp.content
            if not self._validate_pdf(content):
                return FetchResult(
                    paper_id=paper_id,
                    title=title,
                    status="download_failed",
                    error="invalid_content",
                    fetch_url=fetch_url,
                )
            metadata = build_blob_metadata(paper_metadata)
            gcs_uri = await asyncio.to_thread(
                self.gcs.upload,
                filename,
                content,
                "application/pdf",
                metadata,
            )
            return FetchResult(
                paper_id=paper_id,
                title=title,
                status="uploaded",
                gcs_uri=gcs_uri,
                size_bytes=len(content),
                fetch_url=fetch_url,
            )
        except Exception as e:
            return FetchResult(
                paper_id=paper_id,
                title=title,
                status="error",
                error=str(e),
                fetch_url=fetch_url,
            )

    # ── Batch fetch + upload with GCS dedup ──────────────────────────

    async def fetch_batch(
        self,
        papers: List[Dict[str, Any]],
        on_result: Optional[Any] = None,
    ) -> BatchResult:
        """
        Fetch PDFs for a batch of papers with GCS deduplication.

        Before making any API calls, checks which paper_ids already
        have PDFs in GCS and skips them entirely.

        Args:
            papers: List of paper metadata dicts
            on_result: Optional async callback(FetchResult) for progress reporting
        """
        batch = BatchResult()

        if not papers:
            return batch

        papers = [p for p in papers if p.get("paperId")]
        if not papers:
            return batch

        filenames = [paper_id_to_filename(p["paperId"]) for p in papers]
        try:
            existing = await asyncio.to_thread(self.gcs.exists_batch, filenames)
        except Exception as e:
            logger.warning(f"GCS exists_batch failed, skipping dedup: {e}")
            existing = set()

        to_fetch: List[Dict[str, Any]] = []
        for paper, fname in zip(papers, filenames):
            pid = paper.get("paperId", "unknown")
            title = paper.get("title", "untitled")
            if fname in existing:
                result = FetchResult(
                    paper_id=pid, title=title, status="exists",
                    gcs_uri=f"{self.gcs.base_uri}{fname}",
                )
                batch.already_in_gcs += 1
                batch.results.append(result)
                if on_result:
                    await on_result(result)
            else:
                to_fetch.append(paper)

        if not to_fetch:
            return batch

        semaphore = asyncio.Semaphore(self.concurrency)

        async def _fetch_one(paper: Dict[str, Any], client: httpx.AsyncClient) -> FetchResult:
            pid = paper.get("paperId", "unknown")
            title = paper.get("title", "untitled")
            filename = paper_id_to_filename(pid)

            async with semaphore:
                try:
                    resolved = await self.resolve_pdf_url(paper, client)
                    if not resolved:
                        return FetchResult(paper_id=pid, title=title, status="no_pdf")

                    url, source = resolved
                    content = await self.fetch_pdf_bytes(url, client)
                    if content is None:
                        return FetchResult(
                            paper_id=pid, title=title, status="download_failed",
                            source=source, error=f"Failed from {url[:80]}",
                            fetch_url=url,
                        )

                    metadata = build_blob_metadata(paper)
                    gcs_uri = await asyncio.to_thread(
                        self.gcs.upload, filename, content, "application/pdf", metadata
                    )
                    await asyncio.sleep(1)

                    return FetchResult(
                        paper_id=pid, title=title, status="uploaded",
                        gcs_uri=gcs_uri, source=source, size_bytes=len(content),
                    )
                except Exception as e:
                    return FetchResult(
                        paper_id=pid, title=title, status="error", error=str(e),
                    )

        async with httpx.AsyncClient() as client:
            tasks = [_fetch_one(p, client) for p in to_fetch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if isinstance(r, Exception):
                batch.errors += 1
                batch.results.append(FetchResult(
                    paper_id="unknown", title="unknown", status="error", error=str(r),
                ))
                continue

            batch.results.append(r)
            if r.status == "uploaded":
                batch.uploaded += 1
            elif r.status == "no_pdf":
                batch.no_pdf_found += 1
            elif r.status == "download_failed":
                batch.download_failed += 1
            elif r.status == "error":
                batch.errors += 1

            if on_result:
                await on_result(r)

        return batch
