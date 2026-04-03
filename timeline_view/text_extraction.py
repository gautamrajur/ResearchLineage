"""
text_extraction.py - Paper text extraction with tiered fallback

Extraction chain (in order):
    1. arXiv HTML (arxiv.org/html)          → best quality, structured
    2. ar5iv HTML (ar5iv.labs.arxiv.org)    → fallback for arXiv papers
    3. S2 openAccessPdf URL                 → PDF download + pymupdf
    4. Unpaywall API (by DOI)               → finds legal OA PDF
    5. Abstract + TLDR                      → last resort

Install:
    pip install pymupdf beautifulsoup4 requests
"""

import io
import re
import requests
from bs4 import BeautifulSoup

import pymupdf  # pip install pymupdf  (also importable as fitz)

from config import (
    ARXIV_HTML_URLS, HTML_REQUEST_TIMEOUT, VERBOSE,
    UNPAYWALL_EMAIL,   # add to config.py: UNPAYWALL_EMAIL = "you@email.com"
)
from semantic_scholar import get_arxiv_id
from config import logger
print = logger.info


# ── Constants ─────────────────────────────────────────────────────────────────
PDF_REQUEST_TIMEOUT  = 30   # seconds for PDF downloads
UNPAYWALL_TIMEOUT    = 10
MIN_TEXT_CHARS       = 500  # below this, treat as extraction failure


# ══════════════════════════════════════════════════════════════════════════════
# TIER 1 & 2 — arXiv HTML  (unchanged from original)
# ══════════════════════════════════════════════════════════════════════════════

def fetch_html(arxiv_id):
    """Try arxiv.org HTML then ar5iv fallback."""
    for url_template in ARXIV_HTML_URLS:
        url = url_template.format(arxiv_id=arxiv_id)
        try:
            resp = requests.get(url, timeout=HTML_REQUEST_TIMEOUT)
            if resp.status_code == 200 and len(resp.text) > 1000:
                if VERBOSE:
                    print(f"    ✅ HTML fetched from {url}")
                return resp.text, url
        except Exception as e:
            if VERBOSE:
                print(f"    ⚠️  Failed {url}: {e}")
    if VERBOSE:
        print(f"    ❌ No HTML available for {arxiv_id}")
    return None, None


def parse_html(html_content):
    """Parse arXiv/ar5iv HTML into title + sections dict."""
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
            result["sections"]["Abstract"] = re.sub(r'^Abstract\s*', '', text)

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
    name = re.sub(r'^[\d]+[\.\d]*\s*', '', _clean_text(heading.get_text())).strip()
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
    return re.sub(r'\s+', ' ', text or '').strip()


# ══════════════════════════════════════════════════════════════════════════════
# TIER 3 — PDF extraction with PyMuPDF
# ══════════════════════════════════════════════════════════════════════════════

def extract_text_from_pdf_bytes(pdf_bytes):
    """
    Extract plain text from a PDF given its raw bytes using PyMuPDF.
    Returns text string or None if extraction fails / too short.
    """
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        pages = []
        for page in doc:
            text = page.get_text()
            if text.strip():
                pages.append(text)
        doc.close()
        full_text = "\n\n".join(pages)
        if len(full_text) < MIN_TEXT_CHARS:
            return None
        return full_text
    except Exception as e:
        if VERBOSE:
            print(f"    ❌ PyMuPDF extraction failed: {e}")
        return None


def fetch_pdf_bytes(url):
    """Download a PDF URL and return raw bytes, or None on failure."""
    try:
        resp = requests.get(
            url,
            timeout=PDF_REQUEST_TIMEOUT,
            headers={"User-Agent": "ResearchLineage/1.0 (academic research tool)"},
            allow_redirects=True,
        )
        if resp.status_code == 200 and resp.content:
            # Verify it's actually a PDF
            if resp.content[:4] == b'%PDF' or 'pdf' in resp.headers.get('content-type', '').lower():
                return resp.content
        if VERBOSE:
            print(f"    ❌ PDF fetch failed ({resp.status_code}): {url}")
    except Exception as e:
        if VERBOSE:
            print(f"    ❌ PDF fetch error: {e}")
    return None


def try_s2_open_access_pdf(paper_data):
    """
    Tier 3a: Try S2 openAccessPdf field — already in paper metadata, no API call.
    Returns extracted text or None.
    """
    oa = paper_data.get("openAccessPdf") or {}
    pdf_url = oa.get("url")
    if not pdf_url:
        return None

    if VERBOSE:
        print(f"    📎 Trying S2 openAccessPdf: {pdf_url[:80]}...")

    pdf_bytes = fetch_pdf_bytes(pdf_url)
    if pdf_bytes:
        text = extract_text_from_pdf_bytes(pdf_bytes)
        if text:
            if VERBOSE:
                print(f"    ✅ S2 PDF extracted ({len(text):,} chars)")
            return text
    return None


# ══════════════════════════════════════════════════════════════════════════════
# TIER 4 — Unpaywall (raw REST API, no external package)
# ══════════════════════════════════════════════════════════════════════════════

def get_doi(paper_data):
    """Extract DOI from paper_data externalIds."""
    return (paper_data.get("externalIds") or {}).get("DOI")


def try_unpaywall(paper_data):
    """
    Tier 4: Query Unpaywall REST API by DOI to find a legal OA PDF.
    Requires UNPAYWALL_EMAIL set in config.py.
    Returns extracted text or None.

    API: GET https://api.unpaywall.org/v2/{doi}?email={email}
    Response field: best_oa_location.url_for_pdf
    """
    if not UNPAYWALL_EMAIL:
        return None

    doi = get_doi(paper_data)
    if not doi:
        return None

    if VERBOSE:
        print(f"    🔍 Trying Unpaywall for DOI: {doi}")

    try:
        resp = requests.get(
            f"https://api.unpaywall.org/v2/{doi}",
            params={"email": UNPAYWALL_EMAIL},
            timeout=UNPAYWALL_TIMEOUT,
        )
        if resp.status_code != 200:
            if VERBOSE:
                print(f"    ⚠️  Unpaywall returned {resp.status_code}")
            return None

        data = resp.json()
        if not data.get("is_oa"):
            if VERBOSE:
                print(f"    ℹ️  Unpaywall: paper is not OA")
            return None

        best = data.get("best_oa_location") or {}
        pdf_url = best.get("url_for_pdf")

        if not pdf_url:
            # Try all OA locations for a PDF link
            for loc in data.get("oa_locations", []):
                if loc.get("url_for_pdf"):
                    pdf_url = loc["url_for_pdf"]
                    break

        if not pdf_url:
            if VERBOSE:
                print(f"    ℹ️  Unpaywall: no PDF URL found")
            return None

        if VERBOSE:
            print(f"    📎 Unpaywall PDF: {pdf_url[:80]}...")

        pdf_bytes = fetch_pdf_bytes(pdf_url)
        if pdf_bytes:
            text = extract_text_from_pdf_bytes(pdf_bytes)
            if text:
                if VERBOSE:
                    print(f"    ✅ Unpaywall PDF extracted ({len(text):,} chars)")
                return text

    except Exception as e:
        if VERBOSE:
            print(f"    ❌ Unpaywall error: {e}")

    return None


# ══════════════════════════════════════════════════════════════════════════════
# TIER 5 — Abstract + TLDR fallback (formatting helpers)
# ══════════════════════════════════════════════════════════════════════════════

def _format_full_text(title, year, paper_id, sections):
    """Format parsed HTML sections into Gemini-ready text."""
    parts = [f"TITLE: {title}", f"YEAR: {year}",
             f"PAPER_ID: {paper_id}", "SOURCE: FULL_TEXT", ""]
    for name, text in sections.items():
        parts += [f"## {name}", text, ""]
    return "\n".join(parts)


def _format_pdf_text(title, year, paper_id, raw_text, source_label):
    """Format raw PDF text into Gemini-ready text."""
    # Truncate very long PDFs to ~150K chars (~37K tokens) to stay within limits
    if len(raw_text) > 150_000:
        raw_text = raw_text[:150_000] + "\n\n[truncated]"
    return "\n".join([
        f"TITLE: {title}", f"YEAR: {year}",
        f"PAPER_ID: {paper_id}", f"SOURCE: {source_label}", "",
        raw_text,
    ])


def _format_abstract_only(title, year, paper_id, paper_data):
    """Format abstract + TLDR as last resort."""
    parts = [f"TITLE: {title}", f"YEAR: {year}",
             f"PAPER_ID: {paper_id}", "SOURCE: ABSTRACT_ONLY", ""]
    abstract = paper_data.get("abstract")
    if abstract:
        parts += ["## Abstract", abstract, ""]
    tldr = paper_data.get("tldr")
    if tldr and tldr.get("text"):
        parts += ["## TLDR", tldr["text"], ""]
    return "\n".join(parts)


# ══════════════════════════════════════════════════════════════════════════════
# Main entry point  (replaces original extract_paper_text)
# ══════════════════════════════════════════════════════════════════════════════

def extract_paper_text(paper_data):
    """
    Extract text for a paper using the tiered fallback chain.

    Tier 1/2: arXiv HTML       → FULL_TEXT
    Tier 3:   S2 openAccessPdf → PDF_S2
    Tier 4:   Unpaywall PDF    → PDF_UNPAYWALL
    Tier 5:   Abstract + TLDR  → ABSTRACT_ONLY

    Returns:
        tuple: (formatted_text, source_type)
    """
    title    = paper_data.get("title", "Unknown")
    year     = paper_data.get("year", "Unknown")
    paper_id = paper_data.get("paperId", "Unknown")

    # Ensure we have full paper details (abstract, externalIds, openAccessPdf)
    if not paper_data.get("externalIds") or not paper_data.get("abstract"):
        if VERBOSE:
            print(f"    📡 Fetching full details for {title[:50]}...")
        from semantic_scholar import get_paper
        full = get_paper(paper_id)
        if full:
            paper_data = full
            title    = paper_data.get("title", title)
            year     = paper_data.get("year", year)

    # ── Tier 1 & 2: arXiv HTML ────────────────────────────────────────────
    arxiv_id = get_arxiv_id(paper_data)
    if arxiv_id:
        if VERBOSE:
            print(f"    📄 Extracting HTML for {arxiv_id}...")
        html, _ = fetch_html(arxiv_id)
        if html:
            parsed = parse_html(html)
            if parsed.get("sections"):
                text = _format_full_text(title, year, paper_id, parsed["sections"])
                return text, "FULL_TEXT"

    # ── Tier 2.5: arXiv PDF (direct) ─────────────────────────────────────
    if arxiv_id:
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
        if VERBOSE:
            print(f"    📄 Trying arXiv PDF: {pdf_url}...")
        pdf_bytes = fetch_pdf_bytes(pdf_url)
        if pdf_bytes:
            raw = extract_text_from_pdf_bytes(pdf_bytes)
            if raw:
                if VERBOSE:
                    print(f"    ✅ arXiv PDF extracted ({len(raw):,} chars)")
                return _format_pdf_text(title, year, paper_id, raw, "PDF_ARXIV"), "PDF_ARXIV"

    # ── Tier 3: S2 openAccessPdf ──────────────────────────────────────────
    if VERBOSE:
        print(f"    📄 Trying S2 openAccessPdf...")
    raw = try_s2_open_access_pdf(paper_data)
    if raw:
        return _format_pdf_text(title, year, paper_id, raw, "PDF_S2"), "PDF_S2"

    # ── Tier 4: Unpaywall ─────────────────────────────────────────────────
    if UNPAYWALL_EMAIL:
        if VERBOSE:
            print(f"    📄 Trying Unpaywall...")
        raw = try_unpaywall(paper_data)
        if raw:
            return _format_pdf_text(title, year, paper_id, raw, "PDF_UNPAYWALL"), "PDF_UNPAYWALL"

    # ── Tier 5: Abstract + TLDR ───────────────────────────────────────────
    if VERBOSE:
        print(f"    📋 Falling back to abstract only for: {title[:50]}")
    return _format_abstract_only(title, year, paper_id, paper_data), "ABSTRACT_ONLY"


# ══════════════════════════════════════════════════════════════════════════════
# Test
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    from semantic_scholar import get_paper

    print("=" * 60)
    print("Testing tiered text extraction")
    print("=" * 60)

    # Test 1: arXiv paper (should hit Tier 1)
    print("\n1️⃣  Transformer paper (expect FULL_TEXT)...")
    paper = get_paper("ARXIV:1706.03762")
    if paper:
        text, src = extract_paper_text(paper)
        print(f"   Source: {src} | Chars: {len(text):,}")

    # Test 2: Older paper without arXiv HTML (should hit PDF tiers)
    print("\n2️⃣  Mikolov RNN LM 2010 (expect PDF or ABSTRACT_ONLY)...")
    paper2 = get_paper("ARXIV:1301.3666")   # closest available arXiv ID
    if paper2:
        text2, src2 = extract_paper_text(paper2)
        print(f"   Source: {src2} | Chars: {len(text2):,}")

    print("\n✅ Done!")