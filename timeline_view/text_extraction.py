"""
text_extraction.py - Paper text extraction from arXiv HTML

Extraction chain:
    1. arxiv.org/html/{id}     (primary)
    2. ar5iv.org/html/{id}     (fallback)
    3. Abstract + TLDR          (last resort)

Extracts all text sections from HTML, not just priority ones.
Gemini is smart enough to find what it needs.
"""

import requests
import re
from bs4 import BeautifulSoup

from config import ARXIV_HTML_URLS, HTML_REQUEST_TIMEOUT, VERBOSE
from semantic_scholar import get_arxiv_id
from config import logger
print = logger.info

# ========================================
# HTML Fetching
# ========================================

def fetch_html(arxiv_id):
    """
    Fetch HTML content for an arXiv paper.
    Tries arxiv.org first, then ar5iv as fallback.

    Args:
        arxiv_id: e.g., "1706.03762"

    Returns:
        tuple: (html_content, source_url) or (None, None)
    """
    for url_template in ARXIV_HTML_URLS:
        url = url_template.format(arxiv_id=arxiv_id)
        try:
            response = requests.get(url, timeout=HTML_REQUEST_TIMEOUT)
            if response.status_code == 200 and len(response.text) > 1000:
                if VERBOSE:
                    print(f"    ✅ HTML fetched from {url}")
                return response.text, url
        except Exception as e:
            if VERBOSE:
                print(f"    ⚠️  Failed {url}: {e}")
            continue

    if VERBOSE:
        print(f"    ❌ No HTML available for {arxiv_id}")
    return None, None


# ========================================
# HTML Parsing
# ========================================

def parse_html(html_content):
    """
    Parse arXiv HTML and extract all text sections.

    arXiv HTML structure:
        <section class="ltx_section">      → top-level sections
        <section class="ltx_subsection">   → subsections
        <div class="ltx_abstract">         → abstract
        <h1 class="ltx_title">             → title
        <p class="ltx_p">                  → paragraphs

    Args:
        html_content: Raw HTML string

    Returns:
        dict: {
            "title": str,
            "sections": OrderedDict of {section_name: text}
        }
    """
    soup = BeautifulSoup(html_content, "html.parser")

    result = {
        "title": None,
        "sections": {}
    }

    # --- Title ---
    title_tag = soup.find("h1", class_="ltx_title")
    if title_tag:
        result["title"] = _clean_text(title_tag.get_text())

    # --- Abstract ---
    abstract_tag = soup.find("div", class_="ltx_abstract")
    if abstract_tag:
        # Abstract often has a heading "Abstract" inside it — skip that
        paragraphs = abstract_tag.find_all("p", class_="ltx_p")
        if paragraphs:
            result["sections"]["Abstract"] = _join_paragraphs(paragraphs)
        else:
            text = _clean_text(abstract_tag.get_text())
            # Remove leading "Abstract" word if present
            text = re.sub(r'^Abstract\s*', '', text)
            result["sections"]["Abstract"] = text

    # --- All sections ---
    for section in soup.find_all("section", class_="ltx_section"):
        name, text = _extract_section(section)
        if name and text:
            result["sections"][name] = text

        # Also get subsections within this section
        for subsection in section.find_all("section", class_="ltx_subsection"):
            sub_name, sub_text = _extract_section(subsection)
            if sub_name and sub_text and sub_name not in result["sections"]:
                result["sections"][sub_name] = sub_text

    return result


def _extract_section(section_tag):
    """
    Extract section name and text from a section tag.

    Returns:
        tuple: (section_name, section_text) or (None, None)
    """
    # Find heading
    heading = section_tag.find(["h2", "h3", "h4", "h5", "h6"])
    if not heading:
        return None, None

    name = _clean_text(heading.get_text())
    # Remove numbering like "1", "3.2", "A.1" from start
    name = re.sub(r'^[\d]+[\.\d]*\s*', '', name).strip()

    if not name:
        return None, None

    # Get all paragraphs directly in this section (not nested subsections)
    paragraphs = section_tag.find_all("p", class_="ltx_p", recursive=False)

    # If no direct paragraphs, try all paragraphs (some papers structure differently)
    if not paragraphs:
        paragraphs = section_tag.find_all("p", class_="ltx_p")

    text = _join_paragraphs(paragraphs)

    return name, text


def _join_paragraphs(paragraph_tags):
    """Join paragraph tags into clean text."""
    texts = []
    for p in paragraph_tags:
        text = _clean_text(p.get_text(separator=" "))
        if text:
            texts.append(text)
    return "\n\n".join(texts)


def _clean_text(text):
    """Clean extracted text — remove extra whitespace, newlines."""
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# ========================================
# Main Extraction Function
# ========================================

def extract_paper_text(paper_data):
    """
    Extract text for a paper. Tries HTML, falls back to abstract.

    If paper_data doesn't have abstract or externalIds, fetches
    full details via get_paper() first.

    Args:
        paper_data: Paper dict (may be partial from references endpoint
                    or full from get_paper())

    Returns:
        tuple: (formatted_text, source_type)
            formatted_text: String ready for Gemini input
            source_type: "FULL_TEXT" or "ABSTRACT_ONLY"
    """
    title = paper_data.get("title", "Unknown")
    year = paper_data.get("year", "Unknown")
    paper_id = paper_data.get("paperId", "Unknown")

    # If we don't have externalIds or abstract, fetch full paper details
    # (references endpoint doesn't return abstract due to API limitation)
    if not paper_data.get("externalIds") or not paper_data.get("abstract"):
        if VERBOSE:
            print(f"    📡 Fetching full details for {title[:50]}...")
        from semantic_scholar import get_paper
        full_paper = get_paper(paper_id)
        if full_paper:
            paper_data = full_paper
            title = paper_data.get("title", title)
            year = paper_data.get("year", year)

    # Try HTML extraction
    arxiv_id = get_arxiv_id(paper_data)
    extracted = None

    if arxiv_id:
        if VERBOSE:
            print(f"    📄 Extracting HTML for {arxiv_id}...")
        html_content, source_url = fetch_html(arxiv_id)
        if html_content:
            extracted = parse_html(html_content)

    # Build formatted text
    if extracted and extracted.get("sections"):
        text = _format_full_text(title, year, paper_id, extracted["sections"])
        return text, "FULL_TEXT"
    else:
        text = _format_abstract_only(title, year, paper_id, paper_data)
        return text, "ABSTRACT_ONLY"


def _format_full_text(title, year, paper_id, sections):
    """Format extracted sections into Gemini-ready text."""
    parts = [
        f"TITLE: {title}",
        f"YEAR: {year}",
        f"PAPER_ID: {paper_id}",
        f"SOURCE: FULL_TEXT",
        ""
    ]

    for section_name, section_text in sections.items():
        parts.append(f"## {section_name}")
        parts.append(section_text)
        parts.append("")

    return "\n".join(parts)


def _format_abstract_only(title, year, paper_id, paper_data):
    """Format abstract + TLDR as fallback."""
    parts = [
        f"TITLE: {title}",
        f"YEAR: {year}",
        f"PAPER_ID: {paper_id}",
        f"SOURCE: ABSTRACT_ONLY",
        ""
    ]

    abstract = paper_data.get("abstract")
    if abstract:
        parts.append("## Abstract")
        parts.append(abstract)
        parts.append("")

    tldr = paper_data.get("tldr")
    if tldr and tldr.get("text"):
        parts.append("## TLDR")
        parts.append(tldr["text"])
        parts.append("")

    return "\n".join(parts)


# ========================================
# Test
# ========================================

if __name__ == "__main__":
    from semantic_scholar import get_paper

    print("=" * 60)
    print("Testing Text Extraction Module")
    print("=" * 60)

    # Test 1: Fetch and parse HTML
    print("\n1️⃣  Testing HTML extraction for Transformer paper...")
    paper = get_paper("ARXIV:1706.03762")
    if paper:
        text, source_type = extract_paper_text(paper)
        print(f"\n   Source type: {source_type}")
        print(f"   Text length: {len(text)} chars")
        print(f"   Approx tokens: ~{len(text) // 4}")

        # Show sections found
        arxiv_id = get_arxiv_id(paper)
        html_content, _ = fetch_html(arxiv_id)
        if html_content:
            parsed = parse_html(html_content)
            print(f"\n   Sections found ({len(parsed['sections'])}):")
            for name, content in parsed["sections"].items():
                print(f"     - {name}: {len(content)} chars")

        # Show preview
        print(f"\n   Preview (first 500 chars):")
        print(f"   {text[:500]}")

    # Test 2: Test abstract fallback
    print("\n\n2️⃣  Testing abstract fallback (paper without arXiv HTML)...")
    # Use a fake paper dict to test fallback
    fake_paper = {
        "paperId": "test123",
        "title": "Some Old Paper",
        "year": 1990,
        "abstract": "This paper introduces a method for doing something important.",
        "tldr": {"text": "A method for something important."},
        "externalIds": {}  # No arXiv ID
    }
    text, source_type = extract_paper_text(fake_paper)
    print(f"   Source type: {source_type}")
    print(f"   Text:\n{text}")

    print("\n✅ Done!")