"""
evolution_view/text_extraction.py
----------------------------------
Paper text extraction with tiered fallback (unchanged logic, updated imports).

Extraction chain:
    1. arXiv HTML       → FULL_TEXT
    2. arXiv PDF        → PDF_ARXIV
    3. S2 openAccessPdf → PDF_S2
    4. Unpaywall        → PDF_UNPAYWALL
    5. OpenAlex         → PDF_OPENALEX
    6. Abstract + TLDR  → ABSTRACT_ONLY
"""

import io
import re
import requests
from bs4 import BeautifulSoup
import pymupdf

from ..common.config import (
    ARXIV_HTML_URLS, HTML_REQUEST_TIMEOUT, VERBOSE, UNPAYWALL_EMAIL, logger,
)
from ..common.s2_client import SemanticScholarClient

print = logger.info

PDF_REQUEST_TIMEOUT = 30
UNPAYWALL_TIMEOUT   = 10
MIN_TEXT_CHARS      = 500


# ── Tier 1/2 — arXiv HTML ─────────────────────────────────────────────────────

def fetch_html(arxiv_id):
    for url_template in ARXIV_HTML_URLS:
        url = url_template.format(arxiv_id=arxiv_id)
        try:
            resp = requests.get(url, timeout=HTML_REQUEST_TIMEOUT)
            if resp.status_code == 200 and len(resp.text) > 1000:
                if VERBOSE:
                    print(f"    HTML fetched from {url}")
                return resp.text, url
        except Exception as e:
            if VERBOSE:
                print(f"    Failed {url}: {e}")
    return None, None


def parse_html(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
    result = {"title": None, "sections": {}}

    title_tag = soup.find("h1", class_="ltx_title")
    if title_tag:
        result["title"] = _clean_text(title_tag.get_text())

    abstract_tag = soup.find("div", class_="ltx_abstract")
    if abstract_tag:
        paragraphs = abstract_tag.find_all("p", class_="ltx_p")
        if paragraphs:
            result["sections"]["Abstract"] = _join_paragraphs(paragraphs)
        else:
            text = _clean_text(abstract_tag.get_text())
            result["sections"]["Abstract"] = re.sub(r"^Abstract\s*", "", text)

    for section in soup.find_all("section", class_="ltx_section"):
        name, text = _extract_section(section)
        if name and text:
            result["sections"][name] = text
        for sub in section.find_all("section", class_="ltx_subsection"):
            sn, st = _extract_section(sub)
            if sn and st and sn not in result["sections"]:
                result["sections"][sn] = st

    return result


def _extract_section(section_tag):
    heading = section_tag.find(["h2", "h3", "h4", "h5", "h6"])
    if not heading:
        return None, None
    name = re.sub(r"^[\d]+[\.\d]*\s*", "", _clean_text(heading.get_text())).strip()
    if not name:
        return None, None
    paragraphs = section_tag.find_all("p", class_="ltx_p", recursive=False)
    if not paragraphs:
        paragraphs = section_tag.find_all("p", class_="ltx_p")
    return name, _join_paragraphs(paragraphs)


def _join_paragraphs(tags):
    return "\n\n".join(
        _clean_text(p.get_text(separator=" ")) for p in tags
        if _clean_text(p.get_text(separator=" "))
    )


def _clean_text(text):
    return re.sub(r"\s+", " ", text or "").strip()


# ── Tier 3 — PDF via PyMuPDF ──────────────────────────────────────────────────

def extract_text_from_pdf_bytes(pdf_bytes):
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        pages = [page.get_text() for page in doc if page.get_text().strip()]
        doc.close()
        full_text = "\n\n".join(pages)
        return full_text if len(full_text) >= MIN_TEXT_CHARS else None
    except Exception as e:
        if VERBOSE:
            print(f"    PyMuPDF extraction failed: {e}")
        return None


def fetch_pdf_bytes(url):
    try:
        resp = requests.get(
            url, timeout=PDF_REQUEST_TIMEOUT,
            headers={"User-Agent": "ResearchLineage/1.0"},
            allow_redirects=True,
        )
        if resp.status_code == 200 and resp.content:
            if resp.content[:4] == b"%PDF" or "pdf" in resp.headers.get("content-type", "").lower():
                return resp.content
    except Exception as e:
        if VERBOSE:
            print(f"    PDF fetch error: {e}")
    return None


def try_s2_open_access_pdf(paper_data):
    oa = paper_data.get("openAccessPdf") or {}
    pdf_url = oa.get("url")
    if not pdf_url:
        return None
    if VERBOSE:
        print(f"    Trying S2 openAccessPdf: {pdf_url[:80]}...")
    pdf_bytes = fetch_pdf_bytes(pdf_url)
    if pdf_bytes:
        text = extract_text_from_pdf_bytes(pdf_bytes)
        if text:
            if VERBOSE:
                print(f"    S2 PDF extracted ({len(text):,} chars)")
            return text
    return None


# ── Tier 4 — Unpaywall ────────────────────────────────────────────────────────

def get_doi(paper_data):
    return (paper_data.get("externalIds") or {}).get("DOI")


def try_unpaywall(paper_data):
    if not UNPAYWALL_EMAIL:
        return None
    doi = get_doi(paper_data)
    if not doi:
        return None
    if VERBOSE:
        print(f"    Trying Unpaywall for DOI: {doi}")
    try:
        resp = requests.get(
            f"https://api.unpaywall.org/v2/{doi}",
            params={"email": UNPAYWALL_EMAIL},
            timeout=UNPAYWALL_TIMEOUT,
        )
        if resp.status_code != 200 or not resp.json().get("is_oa"):
            return None
        data = resp.json()
        best = data.get("best_oa_location") or {}
        pdf_url = best.get("url_for_pdf")
        if not pdf_url:
            for loc in data.get("oa_locations", []):
                if loc.get("url_for_pdf"):
                    pdf_url = loc["url_for_pdf"]
                    break
        if not pdf_url:
            return None
        pdf_bytes = fetch_pdf_bytes(pdf_url)
        if pdf_bytes:
            text = extract_text_from_pdf_bytes(pdf_bytes)
            if text:
                if VERBOSE:
                    print(f"    Unpaywall PDF extracted ({len(text):,} chars)")
                return text
    except Exception as e:
        if VERBOSE:
            print(f"    Unpaywall error: {e}")
    return None


# ── Tier 5 — OpenAlex ─────────────────────────────────────────────────────────

def try_openalex(paper_data):
    title = paper_data.get("title", "")
    year  = paper_data.get("year")
    if not title:
        return None
    try:
        resp = requests.get(
            "https://api.openalex.org/works",
            params={
                "filter": f"title.search:{title}",
                "select": "title,publication_year,open_access",
                "per-page": 5,
                "mailto": UNPAYWALL_EMAIL,
            },
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        for result in resp.json().get("results", []):
            result_year = result.get("publication_year")
            if year and result_year and abs(int(result_year) - int(year)) > 1:
                continue
            oa_url = (result.get("open_access") or {}).get("oa_url")
            if not oa_url:
                continue
            pdf_bytes = fetch_pdf_bytes(oa_url)
            if pdf_bytes:
                text = extract_text_from_pdf_bytes(pdf_bytes)
                if text:
                    return text
    except Exception as e:
        if VERBOSE:
            print(f"    OpenAlex error: {e}")
    return None


# ── Formatters ────────────────────────────────────────────────────────────────

def _format_full_text(title, year, paper_id, sections):
    parts = [f"TITLE: {title}", f"YEAR: {year}", f"PAPER_ID: {paper_id}", "SOURCE: FULL_TEXT", ""]
    for name, text in sections.items():
        parts += [f"## {name}", text, ""]
    return "\n".join(parts)


def _format_pdf_text(title, year, paper_id, raw_text, source_label):
    if len(raw_text) > 150_000:
        raw_text = raw_text[:150_000] + "\n\n[truncated]"
    return "\n".join([
        f"TITLE: {title}", f"YEAR: {year}",
        f"PAPER_ID: {paper_id}", f"SOURCE: {source_label}", "", raw_text,
    ])


def _format_abstract_only(title, year, paper_id, paper_data):
    parts = [f"TITLE: {title}", f"YEAR: {year}", f"PAPER_ID: {paper_id}", "SOURCE: ABSTRACT_ONLY", ""]
    abstract = paper_data.get("abstract")
    if abstract:
        parts += ["## Abstract", abstract, ""]
    tldr = paper_data.get("tldr")
    if tldr and tldr.get("text"):
        parts += ["## TLDR", tldr["text"], ""]
    return "\n".join(parts)


# ── Main entry point ──────────────────────────────────────────────────────────

def extract_paper_text(paper_data):
    """
    Extract text for a paper using the tiered fallback chain.
    Returns (formatted_text, source_type).
    """
    title    = paper_data.get("title", "Unknown")
    year     = paper_data.get("year", "Unknown")
    paper_id = paper_data.get("paperId", "Unknown")

    arxiv_id = SemanticScholarClient.get_arxiv_id(paper_data)

    # Tier 1/2 — arXiv HTML
    if arxiv_id:
        html, _ = fetch_html(arxiv_id)
        if html:
            parsed = parse_html(html)
            if parsed.get("sections"):
                return _format_full_text(title, year, paper_id, parsed["sections"]), "FULL_TEXT"

    # Tier 2.5 — arXiv PDF
    if arxiv_id:
        pdf_bytes = fetch_pdf_bytes(f"https://arxiv.org/pdf/{arxiv_id}")
        if pdf_bytes:
            raw = extract_text_from_pdf_bytes(pdf_bytes)
            if raw:
                return _format_pdf_text(title, year, paper_id, raw, "PDF_ARXIV"), "PDF_ARXIV"

    # Tier 3 — S2 openAccessPdf
    raw = try_s2_open_access_pdf(paper_data)
    if raw:
        return _format_pdf_text(title, year, paper_id, raw, "PDF_S2"), "PDF_S2"

    # Tier 4 — Unpaywall
    if UNPAYWALL_EMAIL:
        raw = try_unpaywall(paper_data)
        if raw:
            return _format_pdf_text(title, year, paper_id, raw, "PDF_UNPAYWALL"), "PDF_UNPAYWALL"

    # Tier 5 — OpenAlex
    if UNPAYWALL_EMAIL:
        raw = try_openalex(paper_data)
        if raw:
            return _format_pdf_text(title, year, paper_id, raw, "PDF_OPENALEX"), "PDF_OPENALEX"

    # Tier 6 — Abstract only
    if VERBOSE:
        print(f"    Falling back to abstract only: {title[:50]}")
    return _format_abstract_only(title, year, paper_id, paper_data), "ABSTRACT_ONLY"
