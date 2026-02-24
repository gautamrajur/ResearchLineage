"""
lineage_pipeline.py
====================
Self-contained end-to-end pipeline for generating fine-tuning data.
No external project imports — everything is inlined.

Steps:
    1. seed_generation        — Pick seed papers from Semantic Scholar
    2. batch_run              — Run lineage tracing pipeline per seed
    3. preprocessing          — Validate raw training data
    4. repair                 — Fix foundational entries with missing lineage chains
    5. split                  — Cluster-level stratified train/val/test split
    6. convert                — Convert to Llama chat format + metadata sidecars
    7. report                 — Generate pipeline_report.json + pipeline_report.txt
    8. upload                 — Upload entire pipeline_output/ folder to GCS

Logging:
    Console: INFO and above
    File:    DEBUG and above → pipeline_output/pipeline.log
"""

import argparse
import json
import logging
import os
import random
import re
import sys
import time
import traceback
import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from google import genai
from google.genai import types


# ════════════════════════════════════════
# CONFIG — imported from src/utils/config.py
# ════════════════════════════════════════

# Add project root to path so src.utils.config is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.utils.config import (
    # Semantic Scholar
    S2_BASE_URL, S2_API_KEY, S2_REQUEST_TIMEOUT, S2_MAX_RETRIES, S2_RETRY_BASE_WAIT,
    # Gemini
    GEMINI_API_KEY, GEMINI_MODEL, GEMINI_TEMPERATURE, GEMINI_MAX_OUTPUT_TOKENS,
    # arXiv
    ARXIV_HTML_URLS, HTML_REQUEST_TIMEOUT,
    # Pipeline
    MAX_DEPTH, MAX_CANDIDATES, MAX_SEEDS_PER_RUN, BATCH_SLEEP_BETWEEN_SEEDS,
    # Seeds
    SEED_DOMAINS, SEED_MIN_CITATIONS, SEED_PER_DOMAIN_POOL,
    SEED_DEFAULT_COUNT, SEED_QUERY, SEED_RANDOM_SEED,
    # Split
    FINE_TUNING_ALLOWED_FIELDS, SPLIT_TRAIN_FRAC, SPLIT_VAL_FRAC,
    SPLIT_TEST_FRAC, SPLIT_RANDOM_SEED,
    # GCS
    GCS_BUCKET_NAME, GCS_PROJECT_ID, GCS_UPLOAD_PREFIX,
    # Paths
    RUN_DIR, SEEDS_FILE, TRAINING_DATA_FILE, REPAIRED_DATA_FILE,
    SPLITS_DIR, LLAMA_FORMAT_DIR, TIMELINE_OUTPUT_DIR,
    STATE_FILE, REPORT_JSON, REPORT_TXT, LOG_FILE,
    # Prompts
    MAIN_PROMPT, FOUNDATIONAL_PROMPT,
    # Logging
    VERBOSE,
)
from src.utils.logging import get_logger


# ════════════════════════════════════════
# LOGGING — console via central config + file handler for persistent pipeline log
# ════════════════════════════════════════

logger = get_logger(__name__)

# Add file handler so the full pipeline run is persisted to pipeline_output/pipeline.log
RUN_DIR.mkdir(parents=True, exist_ok=True)
_fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
_fh.setLevel(logging.DEBUG)
_fh.setFormatter(logging.Formatter(
    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
))
logger.addHandler(_fh)


# ════════════════════════════════════════
# SEMANTIC SCHOLAR API
# ════════════════════════════════════════

PAPER_FIELDS = (
    "paperId,externalIds,title,abstract,year,"
    "citationCount,influentialCitationCount,"
    "fieldsOfStudy,s2FieldsOfStudy,"
    "tldr,openAccessPdf,authors"
)

REFERENCE_FIELDS = (
    "citedPaper.paperId,citedPaper.title,"
    "citedPaper.year,citedPaper.citationCount,"
    "citedPaper.externalIds,"
    "isInfluential,intents,contexts"
)


def s2_api_call(endpoint, params=None):
    url = f"{S2_BASE_URL}/{endpoint.lstrip('/')}"
    headers = {"x-api-key": S2_API_KEY} if S2_API_KEY else {}
    logger.debug(f"S2 API call: {endpoint}, params={params}")

    for attempt in range(S2_MAX_RETRIES):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=S2_REQUEST_TIMEOUT)
            if r.status_code == 200:
                logger.debug(f"S2 API success: {endpoint}")
                time.sleep(1.2)
                return r.json()
            elif r.status_code == 429:
                wait = S2_RETRY_BASE_WAIT * (attempt + 1)
                logger.warning(f"S2 rate limited! Waiting {wait}s (attempt {attempt+1}/{S2_MAX_RETRIES})")
                time.sleep(wait)
                continue
            elif r.status_code == 404:
                logger.warning(f"S2 paper not found: {endpoint}")
                return None
            else:
                logger.error(f"S2 error {r.status_code}: {r.text[:200]}")
                return None
        except Exception as e:
            logger.error(f"S2 request failed: {e}")
            return None

    logger.error(f"S2 failed after {S2_MAX_RETRIES} retries: {endpoint}")
    return None


def normalize_paper_id(paper_id):
    paper_id = paper_id.strip()
    for pattern in [r'arxiv\.org/abs/(\d+\.\d+)', r'arxiv\.org/pdf/(\d+\.\d+)', r'arxiv\.org/html/(\d+\.\d+)']:
        match = re.search(pattern, paper_id)
        if match:
            return f"ARXIV:{match.group(1)}"
    if re.match(r'^\d{4}\.\d{4,5}(v\d+)?$', paper_id):
        return f"ARXIV:{paper_id}"
    if re.match(r'^[a-z-]+/\d+$', paper_id):
        return f"ARXIV:{paper_id}"
    return paper_id


def get_arxiv_id(paper_data):
    return (paper_data.get("externalIds") or {}).get("ArXiv")


def get_paper(paper_id):
    paper_id = normalize_paper_id(paper_id)
    logger.debug(f"Fetching paper: {paper_id}")
    result = s2_api_call(f"paper/{paper_id}", {"fields": PAPER_FIELDS})
    if result:
        logger.info(f"Fetched: {result.get('title', 'Unknown')[:60]} ({result.get('year', '?')})")
    else:
        logger.warning(f"Could not fetch paper: {paper_id}")
    return result


def get_references(paper_id):
    paper_id = normalize_paper_id(paper_id)
    logger.debug(f"Fetching references for: {paper_id}")
    result = s2_api_call(f"paper/{paper_id}/references", {"fields": REFERENCE_FIELDS, "limit": 1000})
    if result and "data" in result:
        refs = result["data"]
        logger.info(f"Total references: {len(refs)}")
        return refs or []
    logger.warning(f"No references found for: {paper_id}")
    return []


def filter_methodology_references(references):
    methodology_refs, influential_refs = [], []

    for ref in references:
        cited = ref.get("citedPaper") or {}
        if not cited.get("paperId") or not cited.get("title"):
            continue

        intents = ref.get("intents") or []
        is_influential = ref.get("isInfluential", False)
        has_methodology = "methodology" in intents

        entry = {
            "paper": cited, "is_influential": is_influential,
            "has_methodology": has_methodology, "intents": intents,
            "contexts": ref.get("contexts") or [],
        }

        if has_methodology:
            methodology_refs.append(entry)
        elif is_influential:
            influential_refs.append(entry)

    if len(methodology_refs) < MAX_CANDIDATES:
        methodology_ids = {e["paper"]["paperId"] for e in methodology_refs}
        for entry in influential_refs:
            if entry["paper"]["paperId"] not in methodology_ids:
                methodology_refs.append(entry)

    methodology_refs.sort(key=lambda c: c["paper"].get("citationCount") or 0, reverse=True)
    top = methodology_refs[:MAX_CANDIDATES]

    logger.info(
        f"Filtered references: {len(references)} -> {len(top)} "
        f"(kept methodology/influential with high impact)"
    )
    logger.debug(f"Methodology refs: {len(methodology_refs)}, influential fallback: {len(influential_refs)}")
    return top


# ════════════════════════════════════════
# TEXT EXTRACTION (arXiv HTML)
# ════════════════════════════════════════

def fetch_html(arxiv_id):
    for url_template in ARXIV_HTML_URLS:
        url = url_template.format(arxiv_id=arxiv_id)
        try:
            r = requests.get(url, timeout=HTML_REQUEST_TIMEOUT)
            r.encoding = "utf-8"
            if r.status_code == 200 and len(r.text) > 1000:
                logger.info(f"HTML fetched from {url}")
                return r.text, url
            logger.debug(f"HTML not available at {url} (status={r.status_code}, len={len(r.text)})")
        except Exception as e:
            logger.warning(f"HTML fetch failed for {url}: {e}")
    logger.debug(f"No HTML available for {arxiv_id}")
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
            text = re.sub(r'^Abstract\s*', '', text)
            result["sections"]["Abstract"] = text

    for section in soup.find_all("section", class_="ltx_section"):
        name, text = _extract_section(section)
        if name and text:
            result["sections"][name] = text
        for subsection in section.find_all("section", class_="ltx_subsection"):
            sub_name, sub_text = _extract_section(subsection)
            if sub_name and sub_text and sub_name not in result["sections"]:
                result["sections"][sub_name] = sub_text

    logger.debug(f"Parsed HTML: {len(result['sections'])} sections")
    return result


def _extract_section(section_tag):
    heading = section_tag.find(["h2", "h3", "h4", "h5", "h6"])
    if not heading:
        return None, None
    name = _clean_text(heading.get_text())
    name = re.sub(r'^[\d]+[\.\d]*\s*', '', name).strip()
    if not name:
        return None, None
    paragraphs = section_tag.find_all("p", class_="ltx_p", recursive=False)
    if not paragraphs:
        paragraphs = section_tag.find_all("p", class_="ltx_p")
    return name, _join_paragraphs(paragraphs)


def _join_paragraphs(paragraph_tags):
    return "\n\n".join(_clean_text(p.get_text(separator=" ")) for p in paragraph_tags if _clean_text(p.get_text(separator=" ")))


def _clean_text(text):
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text).strip()


def extract_paper_text(paper_data):
    title = paper_data.get("title", "Unknown")
    year = paper_data.get("year", "Unknown")
    paper_id = paper_data.get("paperId", "Unknown")

    if not paper_data.get("externalIds") or not paper_data.get("abstract"):
        logger.debug(f"Fetching full details for {title[:50]}...")
        full_paper = get_paper(paper_id)
        if full_paper:
            paper_data = full_paper
            title = paper_data.get("title", title)
            year = paper_data.get("year", year)

    arxiv_id = get_arxiv_id(paper_data)
    extracted = None
    if arxiv_id:
        logger.debug(f"Extracting HTML for {arxiv_id}")
        html_content, _ = fetch_html(arxiv_id)
        if html_content:
            extracted = parse_html(html_content)

    if extracted and extracted.get("sections"):
        parts = [f"TITLE: {title}", f"YEAR: {year}", f"PAPER_ID: {paper_id}", "SOURCE: FULL_TEXT", ""]
        for sname, stext in extracted["sections"].items():
            parts.extend([f"## {sname}", stext, ""])
        logger.debug(f"Extracted FULL_TEXT for {title[:50]} ({len(extracted['sections'])} sections)")
        return "\n".join(parts), "FULL_TEXT"
    else:
        parts = [f"TITLE: {title}", f"YEAR: {year}", f"PAPER_ID: {paper_id}", "SOURCE: ABSTRACT_ONLY", ""]
        abstract = paper_data.get("abstract")
        if abstract:
            parts.extend(["## Abstract", abstract, ""])
        tldr = paper_data.get("tldr")
        if tldr and tldr.get("text"):
            parts.extend(["## TLDR", tldr["text"], ""])
        logger.debug(f"Extracted ABSTRACT_ONLY for {title[:50]}")
        return "\n".join(parts), "ABSTRACT_ONLY"


# ════════════════════════════════════════
# GEMINI ANALYSIS
# ════════════════════════════════════════

_gemini_client = None


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        logger.debug("Initializing Gemini client")
        _gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    return _gemini_client


def build_main_input(target_text, candidates_with_context, original_target_info=None):
    parts = [MAIN_PROMPT]
    if original_target_info:
        parts.append(f"\n{'='*60}")
        parts.append("LINEAGE CONTEXT — READ THIS CAREFULLY")
        parts.append(f"{'='*60}")
        parts.append(f"Original paper being traced: {original_target_info.get('title', 'Unknown')}")
        parts.append(f"Research domain: {original_target_info.get('domain', 'Unknown')}")
        parts.append("")
        parts.append("CRITICAL RULE: You MUST select a predecessor that is in the same research domain.")
        parts.append("If no candidate is in the same domain, STOP and set selected_predecessor_id to null.")

    parts.extend([f"\n{'='*60}", "TARGET PAPER", f"{'='*60}", target_text])
    parts.extend([f"\n{'='*60}", "CANDIDATE PREDECESSOR PAPERS", f"{'='*60}"])

    for i, (paper_data, text, source_type, contexts) in enumerate(candidates_with_context, 1):
        pid = paper_data.get("paperId", "unknown")
        parts.extend([f"\n{'─'*40}", f"CANDIDATE {i} (Paper ID: {pid})", f"{'─'*40}", text])
        if contexts:
            parts.append("\nCITATION CONTEXTS (how target paper cites this paper):")
            for j, ctx in enumerate(contexts[:5], 1):
                parts.append(f'  [{j}] "{ctx}"')

    return "\n".join(parts)


def build_foundational_input(paper_text):
    return "\n".join([FOUNDATIONAL_PROMPT, f"\n{'='*60}", "PAPER TO ANALYZE", f"{'='*60}", paper_text])


def call_gemini(prompt_text, max_retries=3):
    client = _get_gemini_client()
    token_est = len(prompt_text) // 4
    logger.info(f"Sending ~{token_est:,} tokens to Gemini ({GEMINI_MODEL})")

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL, contents=prompt_text,
                config=types.GenerateContentConfig(
                    temperature=GEMINI_TEMPERATURE,
                    max_output_tokens=GEMINI_MAX_OUTPUT_TOKENS,
                    response_mime_type="application/json",
                    thinking_config=types.ThinkingConfig(thinking_budget=1024),
                ),
            )
            if response and response.text:
                logger.info(f"Gemini responded ({len(response.text)} chars)")
                return response.text
            logger.warning("Gemini returned empty response")
            return None
        except Exception as e:
            err = str(e)
            if any(code in err for code in ["503", "UNAVAILABLE", "429"]):
                wait = min(15 * (2 ** attempt) + random.uniform(-4, 4), 300)
                logger.warning(f"Gemini overloaded, waiting {int(wait)}s (attempt {attempt+1}/{max_retries})")
                time.sleep(wait)
                continue
            logger.error(f"Gemini API error: {e}")
            return None
    logger.error(f"Gemini failed after {max_retries} retries")
    return None


def parse_gemini_response(response_text):
    if not response_text:
        return None
    text = response_text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fixed = re.sub(r',\s*([}\]])', r'\1', text)
    ob = fixed.count('{') - fixed.count('}')
    osq = fixed.count('[') - fixed.count(']')
    if ob > 0 or osq > 0:
        fixed = fixed.rstrip().rstrip(',')
        fixed += ']' * osq + '}' * ob
    try:
        return json.loads(fixed)
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {e}")
        logger.debug(f"Raw response (first 500 chars): {text[:500]}")
        return None


def validate_main_response(parsed):
    if not parsed:
        return False
    if parsed.get("selected_predecessor_id") is None:
        return True
    if not parsed.get("selected_predecessor_id"):
        return False
    for f in ["problem_addressed", "core_method", "key_innovation", "breakthrough_level",
              "explanation_eli5", "explanation_intuitive", "explanation_technical"]:
        if not parsed.get("target_analysis", {}).get(f):
            logger.debug(f"Validation missing: target_analysis.{f}")
            return False
    for f in ["what_was_improved", "how_it_was_improved", "why_it_matters", "problem_solved_from_predecessor"]:
        if not parsed.get("comparison", {}).get(f):
            logger.debug(f"Validation missing: comparison.{f}")
            return False
    return True


def validate_foundational_response(parsed):
    if not parsed:
        return False
    for f in ["problem_addressed", "core_method", "key_innovation", "breakthrough_level",
              "explanation_eli5", "explanation_intuitive", "explanation_technical"]:
        if not parsed.get("target_analysis", {}).get(f):
            logger.debug(f"Validation missing: target_analysis.{f}")
            return False
    return True


def analyze_step(target_text, candidates_with_context, original_target_info=None):
    prompt = build_main_input(target_text, candidates_with_context, original_target_info)
    response_text = call_gemini(prompt)
    parsed = parse_gemini_response(response_text)
    if not validate_main_response(parsed):
        logger.warning("Main response validation failed, retrying...")
        response_text = call_gemini(prompt)
        parsed = parse_gemini_response(response_text)
        if not validate_main_response(parsed):
            logger.error("Main response validation failed after retry")
            return None, None, None
    return parsed, prompt, response_text


def analyze_foundational(paper_text):
    prompt = build_foundational_input(paper_text)
    response_text = call_gemini(prompt)
    parsed = parse_gemini_response(response_text)
    if not validate_foundational_response(parsed):
        logger.warning("Foundational response validation failed, retrying...")
        response_text = call_gemini(prompt)
        parsed = parse_gemini_response(response_text)
        if not validate_foundational_response(parsed):
            logger.error("Foundational response validation failed after retry")
            return None, None, None
    return parsed, prompt, response_text


# ════════════════════════════════════════
# DATA EXPORT
# ════════════════════════════════════════

def _build_paper_metadata(paper_data):
    if not paper_data:
        return {}
    fields = paper_data.get("fieldsOfStudy") or []
    s2_fields = paper_data.get("s2FieldsOfStudy") or []
    primary_field = None
    if fields:
        primary_field = fields[0]
    elif s2_fields:
        for f in s2_fields:
            if f.get("source") == "external":
                primary_field = f.get("category")
                break
        if not primary_field and s2_fields:
            primary_field = s2_fields[0].get("category")
    return {
        "paper_id": paper_data.get("paperId"),
        "title": paper_data.get("title"),
        "year": paper_data.get("year"),
        "citation_count": paper_data.get("citationCount"),
        "field_of_study": primary_field,
        "arxiv_id": (paper_data.get("externalIds") or {}).get("ArXiv"),
    }
 


def _example_exists(paper_id):
    if not paper_id or not os.path.exists(TRAINING_DATA_FILE):
        return False
    with open(TRAINING_DATA_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                ex = json.loads(line)
                if ex.get("metadata", {}).get("target_paper_id") == paper_id:
                    return True
            except json.JSONDecodeError:
                continue
    return False


def _count_jsonl(filepath):
    if not os.path.exists(filepath):
        return 0
    with open(filepath, "r", encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def save_training_example(paper_id, instruction, prompt_text, response_text,
                          metadata=None, target_paper=None, candidates=None,
                          predecessor_paper=None, lineage_chain=None):
    os.makedirs(os.path.dirname(TRAINING_DATA_FILE) or ".", exist_ok=True)
    if _example_exists(paper_id):
        logger.debug(f"Training example already exists for {paper_id}, skipping")
        return

    candidate_metadata = []
    if candidates:
        for c in candidates:
            p = c.get("paper", {}) if isinstance(c, dict) and "paper" in c else c
            candidate_metadata.append(_build_paper_metadata(p))

    example = {
        "instruction": instruction, "input": prompt_text,
        "output": response_text, "metadata": metadata or {},
        "level_info": {
            "target_paper": _build_paper_metadata(target_paper) if target_paper else {},
            "predecessor_paper": _build_paper_metadata(predecessor_paper) if predecessor_paper else None,
            "candidates_passed_to_llm": candidate_metadata,
            "lineage_chain": lineage_chain or [],
        },
    }

    with open(TRAINING_DATA_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(example, ensure_ascii=False) + "\n")

    total = _count_jsonl(TRAINING_DATA_FILE)
    logger.info(f"Training example saved for {paper_id} (total: {total})")


def save_timeline_json(timeline_steps, filename=None):
    if not timeline_steps:
        return None

    os.makedirs(TIMELINE_OUTPUT_DIR, exist_ok=True)
    original_target = timeline_steps[0]["target_paper"]

    chain = []
    for step in reversed(timeline_steps):
        target = step["target_paper"]
        analysis = step["analysis"]
        entry = {
            "paper": {"paperId": target.get("paperId"), "title": target.get("title"),
                      "year": target.get("year"), "abstract": target.get("abstract", "")},
            "analysis": analysis.get("target_analysis", {}),
            "source_type": step["target_source_type"],
            "is_foundational": step["is_foundational"],
            "secondary_influences": analysis.get("secondary_influences", []),
            "comparison_with_next": None if step["is_foundational"] else analysis.get("comparison"),
        }
        chain.append(entry)
    for i, entry in enumerate(chain, 1):
        entry["position"] = i

    output = {
        "target_paper": {"paperId": original_target.get("paperId"),
                         "title": original_target.get("title"),
                         "year": original_target.get("year")},
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_papers": len(chain), "total_steps": len(timeline_steps),
        "chain": chain,
    }

    if not filename:
        safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in (original_target.get("title", "unknown")[:40]))
        filename = f"timeline_{safe_title.strip().replace(' ', '_')}.json"

    filepath = os.path.join(TIMELINE_OUTPUT_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    logger.info(f"Timeline saved: {filepath} ({len(chain)} papers)")
    return filepath


# ════════════════════════════════════════
# PIPELINE: build_timeline
# ════════════════════════════════════════

def build_timeline(paper_id, max_depth=MAX_DEPTH):
    logger.info(f"Starting lineage tracing for {paper_id}, max_depth={max_depth}")
    timeline_steps = []
    current_paper_id = paper_id
    visited = set()
    original_target_info = None
    lineage_chain = []

    for depth in range(max_depth):
        logger.info(f"--- Depth {depth+1}/{max_depth} ---")

        if current_paper_id in visited:
            logger.warning(f"Cycle detected: already visited {current_paper_id}, stopping")
            break
        visited.add(current_paper_id)

        target_paper = get_paper(current_paper_id)
        if not target_paper:
            logger.error(f"Could not fetch paper {current_paper_id}, stopping")
            break

        if original_target_info is None:
            abstract = target_paper.get("abstract", "")
            title = target_paper.get("title", "")
            original_target_info = {"title": title, "domain": f"{title}. {abstract[:200]}"}

        target_text, target_source = extract_paper_text(target_paper)
        logger.debug(f"Target text: {target_source}, ~{len(target_text)//4:,} tokens")

        references = get_references(current_paper_id)
        candidates = filter_methodology_references(references) if references else []

        if not candidates:
            logger.info(f"No methodology candidates — treating as FOUNDATIONAL paper")
            step = _handle_foundational(depth, target_paper, target_text, target_source, lineage_chain)
            if step:
                timeline_steps.append(step)
            break

        candidates_with_text = []
        for c in candidates:
            text, src = extract_paper_text(c["paper"])
            candidates_with_text.append((c["paper"], text, src, c["contexts"]))

        analysis, prompt, raw_response = analyze_step(target_text, candidates_with_text, original_target_info)
        if not analysis:
            logger.error("Gemini analysis failed, stopping lineage")
            break

        selected_id = analysis.get("selected_predecessor_id")
        if not selected_id or selected_id == "null":
            logger.info("Gemini found no same-domain predecessor — treating as foundational")
            step = _handle_foundational(depth, target_paper, target_text, target_source, lineage_chain)
            if step:
                step["analysis"]["target_analysis"] = analysis.get("target_analysis", step["analysis"].get("target_analysis", {}))
                timeline_steps.append(step)
            break

        predecessor_paper = None
        for c in candidates:
            if c["paper"].get("paperId") == selected_id:
                predecessor_paper = c["paper"]
                break
        if not predecessor_paper and candidates:
            logger.warning(f"Exact ID match failed for {selected_id}, using first candidate as fallback")
            predecessor_paper = candidates[0]["paper"]
        if not predecessor_paper:
            logger.error("No predecessor found, stopping")
            break

        logger.info(f"PREDECESSOR SELECTED: {predecessor_paper.get('title', '?')[:60]} ({predecessor_paper.get('year', '?')})")

        lineage_chain.append(target_paper.get("paperId"))

        step = {
            "depth": depth, "target_paper": target_paper, "target_text": target_text,
            "target_source_type": target_source, "predecessor_paper": predecessor_paper,
            "candidates_considered": len(candidates), "analysis": analysis, "is_foundational": False,
        }
        timeline_steps.append(step)

        save_training_example(
            paper_id=target_paper["paperId"], instruction=MAIN_PROMPT,
            prompt_text=prompt, response_text=raw_response,
            metadata={
                "target_paper_id": target_paper["paperId"], "target_title": target_paper.get("title"),
                "predecessor_paper_id": predecessor_paper["paperId"], "depth": depth,
                "candidates_considered": len(candidates), "target_source_type": target_source,
                "model": GEMINI_MODEL, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            },
            target_paper=target_paper, candidates=candidates,
            predecessor_paper=predecessor_paper, lineage_chain=list(lineage_chain),
        )

        current_paper_id = predecessor_paper["paperId"]
        time.sleep(1)

    # Check if last predecessor needs foundational analysis
    if timeline_steps and not timeline_steps[-1]["is_foundational"]:
        last_pred = timeline_steps[-1]["predecessor_paper"]
        logger.debug(f"Checking if last predecessor is foundational: {last_pred.get('title', '?')[:50]}")
        last_refs = get_references(last_pred["paperId"])
        last_cands = filter_methodology_references(last_refs) if last_refs else []
        if not last_cands:
            logger.info("Last predecessor is foundational, analyzing...")
            last_text, last_src = extract_paper_text(last_pred)
            last_step = _handle_foundational(len(timeline_steps), last_pred, last_text, last_src, lineage_chain)
            if last_step:
                timeline_steps.append(last_step)

    logger.info(f"Timeline complete: {len(timeline_steps)} papers traced")
    return timeline_steps


def _handle_foundational(depth, paper, paper_text, source_type, lineage_chain=None):
    logger.info(f"Running foundational analysis for: {paper.get('title', '?')[:60]}")
    analysis, prompt, raw_response = analyze_foundational(paper_text)
    if not analysis:
        logger.error("Foundational analysis failed")
        return None

    bt = analysis.get("target_analysis", {}).get("breakthrough_level", "?")
    logger.info(f"Foundational paper analyzed (breakthrough: {bt})")

    lc = list(lineage_chain or []) + [paper["paperId"]]

    save_training_example(
        paper_id=paper["paperId"], instruction=FOUNDATIONAL_PROMPT,
        prompt_text=prompt, response_text=raw_response,
        metadata={
            "target_paper_id": paper["paperId"], "target_title": paper.get("title"),
            "predecessor_paper_id": None, "depth": depth,
            "candidates_considered": 0, "target_source_type": source_type,
            "is_foundational": True, "model": GEMINI_MODEL,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
        target_paper=paper, candidates=None,
        predecessor_paper=None, lineage_chain=lc,
    )

    return {
        "depth": depth, "target_paper": paper, "target_text": paper_text,
        "target_source_type": source_type, "predecessor_paper": None,
        "candidates_considered": 0, "analysis": analysis, "is_foundational": True,
    }


# ════════════════════════════════════════
# SEED PICKER
# ════════════════════════════════════════

def _s2_bulk_search(field_of_study, pool_size, query, min_citations):
    logger.debug(f"Bulk search: field={field_of_study}, pool={pool_size}, min_cites={min_citations}")
    results, token = [], None
    while len(results) < pool_size:
        params = {
            "query": query, "fields": "paperId,title,year,citationCount,externalIds",
            "limit": min(1000, pool_size - len(results)),
            "sort": "citationCount:desc", "minCitationCount": min_citations,
            "fieldsOfStudy": field_of_study, "year": "2000-", "openAccessPdf": "",
        }
        if token:
            params["token"] = token
        data = s2_api_call("paper/search/bulk", params)
        if not data:
            break
        batch = data.get("data") or []
        if not batch:
            break
        results.extend(batch)
        token = data.get("token")
        if not token:
            break
        time.sleep(1.0)
    logger.debug(f"Bulk search returned {len(results)} results")
    return results[:pool_size]


def pick_seeds(n_total, domains, per_domain_pool, seed, min_citations, query):
    logger.info(f"Picking {n_total} seeds from domains: {domains}")
    random.seed(seed)
    seeds, seen_ids = [], set()

    for domain in domains:
        per_domain_target = max(1, n_total // len(domains))
        logger.info(f"Domain: {domain} | building pool of {per_domain_pool}")

        pool = _s2_bulk_search(domain, per_domain_pool, query, min_citations)
        logger.info(f"Pool fetched: {len(pool)} papers from {domain}")

        random.shuffle(pool)
        count = 0
        for p in pool:
            pid = p.get("paperId")
            ext = p.get("externalIds") or {}
            if not pid or pid in seen_ids or "ArXiv" not in ext:
                continue
            seeds.append({
                "paperId": pid, "title": p.get("title"), "year": p.get("year"),
                "citationCount": p.get("citationCount"), "domain": domain,
                "arxiv_id": ext.get("ArXiv"),
            })
            seen_ids.add(pid)
            count += 1
            if count >= per_domain_target:
                break

        logger.info(f"Sampled {count} ArXiv seeds from {domain}")
        if len(seeds) >= n_total:
            break

    logger.info(f"Total seeds selected: {len(seeds[:n_total])}")
    return seeds[:n_total]


# ════════════════════════════════════════
# BATCH RUN
# ════════════════════════════════════════

def _load_done_seed_ids(state_file):
    done = set()
    if not os.path.exists(state_file):
        return done
    with open(state_file, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                if rec.get("status") == "success":
                    pid = rec.get("seed_paper_id")
                    if pid:
                        done.add(pid)
            except json.JSONDecodeError:
                continue
    return done


def _append_state(state_file, record):
    os.makedirs(os.path.dirname(state_file) or ".", exist_ok=True)
    with open(state_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _safe_filename(text, max_len=80):
    if not text:
        return "unknown"
    cleaned = "".join(c if c.isalnum() or c in " -_" else "" for c in text.strip())
    return (cleaned.strip().replace(" ", "_") or "unknown")[:max_len]


def run_batch(seeds, depth, max_seeds, sleep, state_file=STATE_FILE, resume=True):
    done = _load_done_seed_ids(state_file) if resume else set()

    run_list = []
    for s in seeds:
        pid = s.get("paperId")
        if not pid:
            continue
        if resume and pid in done:
            logger.debug(f"Skipping already-done seed: {pid}")
            continue
        run_list.append(s)
        if len(run_list) >= max_seeds:
            break

    if not run_list:
        logger.info("Nothing to run (all done or no valid seeds)")
        return 0

    logger.info(f"Batch run starting: {len(run_list)} seeds, depth={depth}")

    successes, failures = 0, 0
    for idx, seed in enumerate(run_list, 1):
        seed_id = seed.get("paperId")
        title = seed.get("title")
        domain = seed.get("domain")

        logger.info(f"=== Seed {idx}/{len(run_list)}: {title or seed_id} (domain={domain}) ===")

        try:
            timeline = build_timeline(seed_id, max_depth=depth)
            if timeline:
                tname = title or (timeline[0].get("target_paper", {}).get("title", ""))
                fname = f"seed_{_safe_filename(seed_id, 16)}_{_safe_filename(tname, 30)}.json"
                filepath = save_timeline_json(timeline, filename=fname)
                successes += 1
                _append_state(state_file, {
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "seed_paper_id": seed_id,
                    "status": "success", "depth": depth, "timeline_path": filepath,
                    "domain": domain, "title": title,
                })
                logger.info(f"Seed SUCCESS: {filepath}")
            else:
                failures += 1
                _append_state(state_file, {
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "seed_paper_id": seed_id,
                    "status": "failed", "depth": depth, "error": "empty timeline",
                    "domain": domain, "title": title,
                })
                logger.error(f"Seed FAILED: build_timeline returned empty for {seed_id}")

        except KeyboardInterrupt:
            _append_state(state_file, {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "seed_paper_id": seed_id,
                "status": "interrupted", "depth": depth, "domain": domain, "title": title,
            })
            logger.warning("Interrupted by user")
            break

        except Exception as e:
            failures += 1
            _append_state(state_file, {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "seed_paper_id": seed_id,
                "status": "failed", "depth": depth, "error": repr(e),
                "domain": domain, "title": title,
            })
            logger.error(f"Seed EXCEPTION for {seed_id}: {e!r}")
            logger.debug(traceback.format_exc())

        time.sleep(max(0.0, sleep))

    logger.info(f"Batch complete: {successes} successes, {failures} failures")
    return successes


# ════════════════════════════════════════
# STEP FUNCTIONS
# ════════════════════════════════════════

ALL_STEPS = [
    "seed_generation", "batch_run", "preprocessing",
    "repair", "split", "convert", "report", "upload",
]


def step_seed_generation(n_seeds, domains_str, min_citations, per_domain_pool, query, seeds_file):
    domains = [d.strip() for d in domains_str.split(",") if d.strip()]
    seeds = pick_seeds(n_seeds, domains, per_domain_pool, SEED_RANDOM_SEED, min_citations, query)
    os.makedirs(os.path.dirname(seeds_file) or ".", exist_ok=True)
    with open(seeds_file, "w", encoding="utf-8") as f:
        json.dump(seeds, f, indent=2, ensure_ascii=False)
    logger.info(f"Generated {len(seeds)} seed papers -> {seeds_file}")
    return {"seeds_count": len(seeds)}


def step_batch_run(seeds_file, max_depth, max_seeds, sleep):
    with open(seeds_file, "r", encoding="utf-8") as f:
        raw = json.load(f)
    seeds = []
    for item in raw:
        if isinstance(item, str):
            seeds.append({"paperId": item})
        elif isinstance(item, dict):
            pid = item.get("paperId") or item.get("paper_id")
            if pid:
                seeds.append({**item, "paperId": pid})
    count = run_batch(seeds, max_depth, max_seeds, sleep)
    lines = _count_jsonl(TRAINING_DATA_FILE)
    logger.info(f"Batch run complete. {lines} training examples total")
    return {"training_examples": lines, "successes": count}


def step_preprocessing(input_path):
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Training data not found: {input_path}")
    total, valid, invalid = 0, 0, 0
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            total += 1
            try:
                entry = json.loads(line)
                if entry.get("output") and entry.get("input"):
                    valid += 1
                else:
                    invalid += 1
            except json.JSONDecodeError:
                invalid += 1
    if valid == 0:
        raise ValueError("No valid training examples found")
    logger.info(f"Preprocessing: {total} total, {valid} valid, {invalid} invalid")
    if invalid > 0:
        logger.warning(f"{invalid} invalid entries found in training data")
    return {"total": total, "valid": valid, "invalid": invalid}


def step_repair(input_path, output_path):
    entries = _load_jsonl(input_path)
    logger.info(f"Repairing lineage chains for {len(entries)} entries")

    chain_map = {}
    for entry in entries:
        li = entry.get("level_info", {}) or {}
        chain = li.get("lineage_chain", [])
        if chain:
            seed_id = chain[0]
            for pid in chain:
                chain_map[pid] = (seed_id, chain)

    fixed = 0
    for entry in entries:
        li = entry.get("level_info", {}) or {}
        tp = li.get("target_paper", {}) or {}
        paper_id = tp.get("paper_id")
        if not li.get("lineage_chain") and paper_id:
            if paper_id in chain_map:
                seed_id, full_chain = chain_map[paper_id]
                li["lineage_chain"] = full_chain + [paper_id]
                if "metadata" in entry:
                    entry["metadata"]["seed_paper_id"] = seed_id
                fixed += 1
                logger.debug(f"Repaired chain for {paper_id}")
            else:
                for e2 in entries:
                    m2 = e2.get("metadata", {})
                    if m2.get("predecessor_paper_id") == paper_id:
                        chain2 = e2.get("level_info", {}).get("lineage_chain", [])
                        if chain2:
                            li["lineage_chain"] = chain2 + [paper_id]
                            if "metadata" in entry:
                                entry["metadata"]["seed_paper_id"] = chain2[0]
                            fixed += 1
                            logger.debug(f"Repaired chain for {paper_id} via predecessor lookup")
                            break

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    logger.info(f"Repaired {fixed}/{len(entries)} lineage chains -> {output_path}")
    return {"total": len(entries), "fixed": fixed}


def step_split(input_path, output_dir, train_frac, val_frac, test_frac, seed):
    samples = _load_jsonl(input_path)
    logger.info(f"Splitting {len(samples)} samples (train={train_frac}, val={val_frac}, test={test_frac})")

    df = _extract_metadata(samples, FINE_TUNING_ALLOWED_FIELDS)
    df = _compute_lineage_clusters(df)
    df = _assign_popularity_tiers(df)

    profiles = _build_cluster_profiles(df)
    assigned = _assign_clusters_to_splits(profiles, train_frac, val_frac, test_frac, seed)

    cluster_to_split = assigned.set_index("lineage_cluster_id")["split"].to_dict()
    df["split"] = df["lineage_cluster_id"].map(cluster_to_split)

    splits = {name: df[df["split"] == name].copy() for name in ["train", "val", "test"]}
    _export_split_files(splits, samples, output_dir)

    result = {
        "train_count": len(splits["train"]), "val_count": len(splits["val"]),
        "test_count": len(splits["test"]), "total": len(df),
        "clusters": df["lineage_cluster_id"].nunique(),
    }
    logger.info(f"Split: train={result['train_count']}, val={result['val_count']}, test={result['test_count']} ({result['clusters']} clusters)")
    return result


def step_convert(splits_dir, output_dir):
    splits_path = Path(splits_dir)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    result = {}
    for split_name in ["train", "val", "test"]:
        input_file = splits_path / f"{split_name}.jsonl"
        if not input_file.exists():
            result[split_name] = 0
            continue

        samples = _load_jsonl(str(input_file))
        training_path = out / f"{split_name}.jsonl"
        metadata_path = out / f"{split_name}_metadata.jsonl"

        n_converted = 0
        with open(training_path, "w", encoding="utf-8") as tf, \
             open(metadata_path, "w", encoding="utf-8") as mf:
            for i, sample in enumerate(samples):
                user_msg = sample.get("input", "")
                asst_msg = sample.get("output", "")
                if not user_msg or not asst_msg:
                    logger.debug(f"Skipping empty sample {i} in {split_name}")
                    continue

                tf.write(json.dumps({"input_text": user_msg, "output_text": asst_msg}, ensure_ascii=False) + "\n")

                meta = sample.get("metadata", {}) or {}
                level = sample.get("level_info", {}) or {}
                target = level.get("target_paper", {}) or {}
                predecessor = level.get("predecessor_paper", None) or {}

                mf.write(json.dumps({
                    "sample_index": n_converted, "original_index": i,
                    "seed_paper_id": meta.get("target_paper_id", target.get("paper_id")),
                    "seed_paper_year": target.get("year"),
                    "seed_citation_count": target.get("citation_count"),
                    "seed_field_of_study": target.get("field_of_study"),
                    "predecessor_paper_id": meta.get("predecessor_paper_id", predecessor.get("paper_id")),
                    "predecessor_paper_year": predecessor.get("year"),
                    "depth": meta.get("depth", 0),
                    "candidate_list_size": meta.get("candidates_considered", 0),
                    "source_type": meta.get("target_source_type"),
                    "model_used": meta.get("model"),
                    "lineage_chain": level.get("lineage_chain", []),
                    "is_terminal": level.get("predecessor_paper") is None,
                }, ensure_ascii=False) + "\n")
                n_converted += 1
        result[split_name] = n_converted
        logger.info(f"Converted {split_name}: {n_converted} samples")

    return result


# ════════════════════════════════════════
# STEP 7: REPORT (JSON + TXT)
# ════════════════════════════════════════

def step_report(repaired_path, splits_dir, llama_dir):
    """Generate pipeline_report.json and pipeline_report.txt with full distributions."""
    logger.info("Generating pipeline report...")

    report = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "config": {
            "gemini_model": GEMINI_MODEL, "max_depth": MAX_DEPTH,
            "max_candidates": MAX_CANDIDATES,
            "split_fractions": {"train": SPLIT_TRAIN_FRAC, "val": SPLIT_VAL_FRAC, "test": SPLIT_TEST_FRAC},
            "allowed_fields": sorted(FINE_TUNING_ALLOWED_FIELDS),
            "seed_min_citations": SEED_MIN_CITATIONS,
        },
    }

    # Seeds
    if os.path.exists(SEEDS_FILE):
        with open(SEEDS_FILE, "r", encoding="utf-8") as f:
            seeds = json.load(f)
        sd = defaultdict(int)
        sy, sc = [], []
        for s in seeds:
            sd[s.get("domain", "unknown")] += 1
            if s.get("year"): sy.append(s["year"])
            if s.get("citationCount"): sc.append(s["citationCount"])
        report["seeds"] = {"total": len(seeds), "by_domain": dict(sd),
                           "year_range": [min(sy), max(sy)] if sy else None,
                           "citation_stats": _numeric_stats(sc)}

    # Batch run
    if os.path.exists(STATE_FILE):
        states = _load_jsonl(STATE_FILE)
        sc = defaultdict(int)
        for s in states:
            sc[s.get("status", "unknown")] += 1
        report["batch_run"] = {"total_seeds_attempted": len(states), "by_status": dict(sc)}

    # Raw + repaired training data
    if os.path.exists(TRAINING_DATA_FILE):
        report["raw_training_data"] = _training_data_distributions(_load_jsonl(TRAINING_DATA_FILE))
    if os.path.exists(repaired_path):
        report["repaired_training_data"] = _training_data_distributions(_load_jsonl(repaired_path))

    # Per-split
    sr = {}
    for name in ["train", "val", "test"]:
        fp = os.path.join(splits_dir, f"{name}.jsonl")
        if os.path.exists(fp):
            sr[name] = _training_data_distributions(_load_jsonl(fp))
    if sr:
        report["splits"] = sr

    # Llama format
    lr = {}
    for name in ["train", "val", "test"]:
        lf = os.path.join(llama_dir, f"{name}.jsonl")
        mf = os.path.join(llama_dir, f"{name}_metadata.jsonl")
        if os.path.exists(lf):
            samples = _load_jsonl(lf)
            il = [len(s.get("input_text", "")) for s in samples]
            ol = [len(s.get("output_text", "")) for s in samples]
            entry = {
                "count": len(samples),
                "input_char_length": _numeric_stats(il),
                "output_char_length": _numeric_stats(ol),
                "approx_input_tokens": _numeric_stats([l // 4 for l in il]),
                "approx_output_tokens": _numeric_stats([l // 4 for l in ol]),
            }
            if os.path.exists(mf):
                ms = _load_jsonl(mf)
                st, fi = defaultdict(int), defaultdict(int)
                tc = 0
                for m in ms:
                    st[m.get("source_type", "unknown")] += 1
                    fi[m.get("seed_field_of_study", "unknown")] += 1
                    if m.get("is_terminal"): tc += 1
                entry.update({
                    "depth_distribution": _numeric_stats([m.get("depth", 0) for m in ms]),
                    "candidate_list_size": _numeric_stats([m.get("candidate_list_size", 0) for m in ms]),
                    "by_source_type": dict(st), "by_field_of_study": dict(fi),
                    "terminal_samples": tc,
                })
            lr[name] = entry
    if lr:
        report["llama_format"] = lr

    # Integrity
    report["integrity_checks"] = _check_lineage_integrity(splits_dir)

    # File manifest
    manifest = {}
    for dirpath, _, filenames in os.walk(str(RUN_DIR)):
        for fn in filenames:
            fp = os.path.join(dirpath, fn)
            rel = os.path.relpath(fp, str(RUN_DIR))
            manifest[rel] = {"size_bytes": os.path.getsize(fp)}
    report["file_manifest"] = manifest

    # Save JSON
    with open(REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    logger.info(f"JSON report saved -> {REPORT_JSON}")

    # Save TXT
    txt = _build_txt_report(report)
    with open(REPORT_TXT, "w", encoding="utf-8") as f:
        f.write(txt)
    logger.info(f"TXT report saved -> {REPORT_TXT}")

    # Print to console
    logger.info("\n" + txt)
    return report


def _training_data_distributions(samples):
    depths, cand_sizes, years, citations, temporal_gaps = [], [], [], [], []
    fields, source_types, breakthrough_levels, models_used = defaultdict(int), defaultdict(int), defaultdict(int), defaultdict(int)
    foundational_count = 0

    for s in samples:
        meta = s.get("metadata", {}) or {}
        level = s.get("level_info", {}) or {}
        target = level.get("target_paper", {}) or {}
        predecessor = level.get("predecessor_paper", None) or {}

        depths.append(meta.get("depth", 0))
        cand_sizes.append(meta.get("candidates_considered", 0))
        source_types[meta.get("target_source_type", "unknown")] += 1
        models_used[meta.get("model", "unknown")] += 1

        field = target.get("field_of_study")
        if field: fields[field] += 1
        year = target.get("year")
        if year: years.append(year)
        cc = target.get("citation_count")
        if cc is not None: citations.append(cc)
        if meta.get("is_foundational"): foundational_count += 1

        pred_year = (predecessor or {}).get("year") if isinstance(predecessor, dict) else None
        if year and pred_year: temporal_gaps.append(year - pred_year)

        output = s.get("output", "")
        if isinstance(output, str):
            try:
                parsed = json.loads(output)
                bt = parsed.get("target_analysis", {}).get("breakthrough_level")
                if bt: breakthrough_levels[bt] += 1
            except (json.JSONDecodeError, TypeError):
                pass

    return {
        "total_samples": len(samples),
        "foundational_samples": foundational_count,
        "non_foundational_samples": len(samples) - foundational_count,
        "by_field_of_study": dict(fields), "by_source_type": dict(source_types),
        "by_model": dict(models_used), "by_breakthrough_level": dict(breakthrough_levels),
        "depth": _numeric_stats(depths),
        "candidates_considered": _numeric_stats(cand_sizes),
        "year": _numeric_stats(years) if years else None,
        "citation_count": _numeric_stats(citations) if citations else None,
        "temporal_gap_years": _numeric_stats(temporal_gaps) if temporal_gaps else None,
    }


def _numeric_stats(values):
    if not values:
        return None
    arr = np.array(values, dtype=float)
    return {
        "count": len(arr), "mean": round(float(np.mean(arr)), 2),
        "std": round(float(np.std(arr)), 2), "min": float(np.min(arr)),
        "p25": float(np.percentile(arr, 25)), "median": float(np.median(arr)),
        "p75": float(np.percentile(arr, 75)), "max": float(np.max(arr)),
    }


def _check_lineage_integrity(splits_dir):
    splits_data = {}
    for name in ["train", "val", "test"]:
        fp = os.path.join(splits_dir, f"{name}.jsonl")
        if os.path.exists(fp):
            splits_data[name] = _load_jsonl(fp)
    if len(splits_data) < 2:
        return None

    split_paper_ids = {}
    for name, samples in splits_data.items():
        pids = set()
        for s in samples:
            li = s.get("level_info", {}) or {}
            for pid in li.get("lineage_chain", []):
                pids.add(pid)
            tp = li.get("target_paper", {}) or {}
            if tp.get("paper_id"): pids.add(tp["paper_id"])
        split_paper_ids[name] = pids

    checks = {}
    names = list(splits_data.keys())
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            overlap = split_paper_ids[a] & split_paper_ids[b]
            checks[f"{a}_vs_{b}"] = {"shared_paper_ids": len(overlap), "passed": len(overlap) == 0}
    return checks


def _build_txt_report(report):
    """Build human-readable TXT report mirroring the split_and_convert style."""
    lines = []
    w = lines.append

    w("=" * 70)
    w("RESEARCHLINEAGE PIPELINE REPORT")
    w(f"Generated: {report['generated_at']}")
    w("=" * 70)

    # Config
    cfg = report.get("config", {})
    w(f"\nCONFIGURATION")
    w(f"  Model:            {cfg.get('gemini_model')}")
    w(f"  Max depth:        {cfg.get('max_depth')}")
    w(f"  Max candidates:   {cfg.get('max_candidates')}")
    w(f"  Allowed fields:   {', '.join(cfg.get('allowed_fields', []))}")
    sf = cfg.get('split_fractions', {})
    w(f"  Split fractions:  train={sf.get('train')}, val={sf.get('val')}, test={sf.get('test')}")

    # Seeds
    if "seeds" in report:
        s = report["seeds"]
        w(f"\n{'='*60}")
        w("SEED PAPERS")
        w(f"{'='*60}")
        w(f"  Total seeds: {s['total']}")
        w(f"  By domain:")
        for d, c in s.get("by_domain", {}).items():
            w(f"    {d:20s}: {c}")
        if s.get("year_range"):
            w(f"  Year range: {s['year_range'][0]} - {s['year_range'][1]}")
        _write_stats(w, "  Citation count", s.get("citation_stats"))

    # Batch run
    if "batch_run" in report:
        b = report["batch_run"]
        w(f"\n{'='*60}")
        w("BATCH RUN")
        w(f"{'='*60}")
        w(f"  Seeds attempted: {b['total_seeds_attempted']}")
        for status, count in b.get("by_status", {}).items():
            w(f"    {status:12s}: {count}")

    # Training data distributions
    for section_key, section_title in [
        ("raw_training_data", "RAW TRAINING DATA"),
        ("repaired_training_data", "REPAIRED TRAINING DATA"),
    ]:
        if section_key in report:
            _write_distribution_section(w, section_title, report[section_key])

    # Per-split distributions
    if "splits" in report:
        w(f"\n{'='*60}")
        w("PER-SPLIT DISTRIBUTIONS")
        w(f"{'='*60}")
        for name in ["train", "val", "test"]:
            if name in report["splits"]:
                _write_distribution_section(w, f"  {name.upper()} SPLIT", report["splits"][name], indent="  ")

        # Cross-split comparison
        w(f"\n  CROSS-SPLIT COMPARISON (%):")
        all_splits = report["splits"]
        split_names = [n for n in ["train", "val", "test"] if n in all_splits]

        for dim_name, dim_key in [("Field", "by_field_of_study"), ("Source Type", "by_source_type"), ("Breakthrough", "by_breakthrough_level")]:
            all_vals = set()
            for name in split_names:
                all_vals.update(all_splits[name].get(dim_key, {}).keys())
            if not all_vals:
                continue
            w(f"\n  {dim_name} Distribution:")
            header = f"    {'':20s}" + "".join(f"{n:>10s}" for n in split_names)
            w(header)
            for val in sorted(all_vals):
                row = f"    {str(val):20s}"
                for name in split_names:
                    total = all_splits[name]["total_samples"]
                    count = all_splits[name].get(dim_key, {}).get(val, 0)
                    pct = count / total * 100 if total > 0 else 0
                    row += f"{pct:>9.1f}%"
                w(row)

    # Llama format
    if "llama_format" in report:
        w(f"\n{'='*60}")
        w("LLAMA FORMAT")
        w(f"{'='*60}")
        for name in ["train", "val", "test"]:
            if name in report["llama_format"]:
                lf = report["llama_format"][name]
                w(f"\n  {name.upper()}: {lf['count']} samples")
                _write_stats(w, "    Input tokens (approx)", lf.get("approx_input_tokens"))
                _write_stats(w, "    Output tokens (approx)", lf.get("approx_output_tokens"))
                _write_stats(w, "    Depth", lf.get("depth_distribution"))
                if lf.get("by_source_type"):
                    w(f"    Source types: {lf['by_source_type']}")
                if lf.get("by_field_of_study"):
                    w(f"    Fields: {lf['by_field_of_study']}")
                w(f"    Terminal samples: {lf.get('terminal_samples', 0)}")

    # Integrity
    if report.get("integrity_checks"):
        w(f"\n{'='*60}")
        w("INTEGRITY CHECKS")
        w(f"{'='*60}")
        for key, check in report["integrity_checks"].items():
            status = "PASSED" if check["passed"] else f"FAILED ({check['shared_paper_ids']} shared)"
            w(f"  {key}: {status}")

    # File manifest
    if "file_manifest" in report:
        w(f"\n{'='*60}")
        w("FILE MANIFEST")
        w(f"{'='*60}")
        total_bytes = 0
        for rel, info in sorted(report["file_manifest"].items()):
            sz = info["size_bytes"]
            total_bytes += sz
            if sz > 1024 * 1024:
                w(f"  {rel:50s} {sz/1024/1024:>8.1f} MB")
            elif sz > 1024:
                w(f"  {rel:50s} {sz/1024:>8.1f} KB")
            else:
                w(f"  {rel:50s} {sz:>8d} B")
        w(f"\n  TOTAL: {total_bytes/1024/1024:.1f} MB across {len(report['file_manifest'])} files")

    w(f"\n{'='*70}")
    w("END OF REPORT")
    w(f"{'='*70}")

    return "\n".join(lines)


def _write_distribution_section(w, title, data, indent=""):
    w(f"\n{indent}{'='*50}")
    w(f"{indent}{title}")
    w(f"{indent}{'='*50}")
    w(f"{indent}  Total samples:       {data['total_samples']}")
    w(f"{indent}  Foundational:        {data['foundational_samples']}")
    w(f"{indent}  Non-foundational:    {data['non_foundational_samples']}")

    w(f"{indent}  Fields of study:")
    for f, c in data.get("by_field_of_study", {}).items():
        pct = c / data["total_samples"] * 100 if data["total_samples"] > 0 else 0
        w(f"{indent}    {f:20s}: {c:4d} ({pct:5.1f}%)")

    w(f"{indent}  Source types:")
    for s, c in data.get("by_source_type", {}).items():
        pct = c / data["total_samples"] * 100 if data["total_samples"] > 0 else 0
        w(f"{indent}    {s:20s}: {c:4d} ({pct:5.1f}%)")

    if data.get("by_breakthrough_level"):
        w(f"{indent}  Breakthrough levels:")
        for b, c in data["by_breakthrough_level"].items():
            pct = c / data["total_samples"] * 100 if data["total_samples"] > 0 else 0
            w(f"{indent}    {b:20s}: {c:4d} ({pct:5.1f}%)")

    _write_stats(w, f"{indent}  Depth", data.get("depth"))
    _write_stats(w, f"{indent}  Candidates considered", data.get("candidates_considered"))
    _write_stats(w, f"{indent}  Year", data.get("year"))
    _write_stats(w, f"{indent}  Citation count", data.get("citation_count"))
    _write_stats(w, f"{indent}  Temporal gap (years)", data.get("temporal_gap_years"))


def _write_stats(w, label, stats):
    if not stats:
        return
    w(f"{label}:")
    w(f"    count={stats['count']}, mean={stats['mean']:.1f}, std={stats['std']:.1f}")
    w(f"    min={stats['min']:.0f}, p25={stats['p25']:.0f}, median={stats['median']:.0f}, p75={stats['p75']:.0f}, max={stats['max']:.0f}")


# ════════════════════════════════════════
# STEP 8: UPLOAD ENTIRE FOLDER TO GCS
# ════════════════════════════════════════

def step_upload(bucket, project, gcs_prefix):
    from google.cloud import storage
    import shutil

    client = storage.Client(project=project)
    gcs_bucket = client.get_bucket(bucket)

    run_id = time.strftime("%Y%m%d_%H%M%S")
    full_prefix = f"{gcs_prefix}/{run_id}"

    uploaded = 0
    for dirpath, _, filenames in os.walk(str(RUN_DIR)):
        for fn in filenames:
            local_path = os.path.join(dirpath, fn)
            rel_path = os.path.relpath(local_path, str(RUN_DIR))
            gcs_path = f"{full_prefix}/{rel_path}".replace("\\", "/")
            blob = gcs_bucket.blob(gcs_path)
            blob.upload_from_filename(local_path)
            uploaded += 1
            logger.debug(f"Uploaded: {rel_path} -> gs://{bucket}/{gcs_path}")

    # Also mirror to latest/
    latest_prefix = f"{gcs_prefix}/latest"
    for dirpath, _, filenames in os.walk(str(RUN_DIR)):
        for fn in filenames:
            local_path = os.path.join(dirpath, fn)
            rel_path = os.path.relpath(local_path, str(RUN_DIR))
            gcs_path = f"{latest_prefix}/{rel_path}".replace("\\", "/")
            blob = gcs_bucket.blob(gcs_path)
            blob.upload_from_filename(local_path)

    logger.info(f"Uploaded {uploaded} files to gs://{bucket}/{full_prefix}/")
    logger.info(f"Also mirrored to gs://{bucket}/{latest_prefix}/")

    return {"uploaded": uploaded, "gcs_path": f"gs://{bucket}/{full_prefix}"}


# ════════════════════════════════════════
# PRIVATE HELPERS (split logic)
# ════════════════════════════════════════

def _load_jsonl(filepath):
    samples = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                samples.append(json.loads(line))
    return samples


def _extract_metadata(samples, allowed_fields):
    rows = []
    for i, sample in enumerate(samples):
        meta = sample.get("metadata", {}) or {}
        level = sample.get("level_info", {}) or {}
        target = level.get("target_paper", {}) or {}
        predecessor = level.get("predecessor_paper", None)
        is_terminal = predecessor is None
        if is_terminal:
            predecessor = {}

        selected_id = meta.get("predecessor_paper_id")
        if not selected_id:
            output = sample.get("output", "")
            if isinstance(output, str):
                try:
                    parsed = json.loads(output)
                    selected_id = parsed.get("selected_predecessor_id")
                except (json.JSONDecodeError, TypeError):
                    pass

        lineage_chain = level.get("lineage_chain", [])
        seed_domain = target.get("field_of_study")
        candidate_ids = set(re.findall(r"CANDIDATE \d+ \(Paper ID: ([a-f0-9]+)\)", sample.get("input", "")))

        row = {
            "sample_index": i, "is_terminal": is_terminal,
            "seed_paper_id": meta.get("target_paper_id", target.get("paper_id")),
            "seed_paper_year": target.get("year"),
            "seed_citation_count": target.get("citation_count", 0),
            "seed_field_of_study": seed_domain,
            "predecessor_paper_id": selected_id or predecessor.get("paper_id"),
            "predecessor_paper_year": predecessor.get("year"),
            "depth": meta.get("depth", 0),
            "candidate_list_size": meta.get("candidates_considered", 0),
            "source_type": meta.get("target_source_type", "unknown"),
            "lineage_chain": json.dumps(lineage_chain),
            "candidate_ids": json.dumps(list(candidate_ids)),
        }
        row["temporal_gap"] = (row["seed_paper_year"] - row["predecessor_paper_year"]
                               if not is_terminal and row["seed_paper_year"] and row["predecessor_paper_year"]
                               else None)
        rows.append(row)

    df = pd.DataFrame(rows)
    if allowed_fields:
        before = len(df)
        df = df[df["seed_field_of_study"].isin(allowed_fields)].reset_index(drop=True)
        removed = before - len(df)
        if removed > 0:
            logger.warning(f"Removed {removed} samples outside allowed fields")
    df["seed_citation_count"] = df["seed_citation_count"].fillna(0).astype(int)
    return df


def _compute_lineage_clusters(df):
    chains = [set(json.loads(row["lineage_chain"])) or set() for _, row in df.iterrows()]
    parent = list(range(len(df)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    paper_to_samples = defaultdict(list)
    for idx, chain in enumerate(chains):
        for pid in chain:
            paper_to_samples[pid].append(idx)
    for pid, idxs in paper_to_samples.items():
        for j in range(1, len(idxs)):
            union(idxs[0], idxs[j])

    cluster_map, counter, cluster_ids = {}, 0, []
    for idx in range(len(df)):
        root = find(idx)
        if root not in cluster_map:
            cluster_map[root] = counter
            counter += 1
        cluster_ids.append(cluster_map[root])

    df = df.copy()
    df["lineage_cluster_id"] = cluster_ids
    logger.info(f"Lineage clusters: {counter}")
    return df


def _assign_popularity_tiers(df):
    df = df.copy()
    values = df["seed_citation_count"].dropna()
    if len(values) == 0:
        df["popularity_tier"] = "unknown"
        return df
    p20, p40, p60, p80 = [values.quantile(q) for q in [0.2, 0.4, 0.6, 0.8]]
    bins = [-1, p20, p40, p60, p80, float("inf")]
    labels = ["low", "medium", "high", "very_high", "landmark"]
    unique_bins, unique_labels = [bins[0]], []
    for i in range(1, len(bins)):
        if bins[i] > unique_bins[-1]:
            unique_bins.append(bins[i])
            unique_labels.append(labels[i - 1])
    if len(unique_bins) < 2:
        df["popularity_tier"] = "medium"
        return df
    df["popularity_tier"] = pd.cut(df["seed_citation_count"], bins=unique_bins, labels=unique_labels, include_lowest=True)
    logger.debug(f"Popularity tiers: low<={p20:.0f}, med<={p40:.0f}, high<={p60:.0f}, vhigh<={p80:.0f}, landmark>{p80:.0f}")
    return df


def _build_cluster_profiles(df):
    profiles = []
    for cid, g in df.groupby("lineage_cluster_id"):
        profiles.append({
            "lineage_cluster_id": cid, "cluster_size": len(g),
            "cluster_max_year": g["seed_paper_year"].max(),
            "cluster_field": g["seed_field_of_study"].mode().iloc[0],
            "cluster_tier": g["popularity_tier"].mode().iloc[0],
        })
    return pd.DataFrame(profiles)


def _assign_clusters_to_splits(cp, train_frac, val_frac, test_frac, seed):
    rng = np.random.RandomState(seed)
    cp = cp.copy()
    cp["strat_key"] = cp["cluster_field"] + "_" + cp["cluster_tier"].astype(str)
    assignments = {}

    for key, stratum in cp.groupby("strat_key"):
        stratum = stratum.sort_values("cluster_max_year").reset_index(drop=True)
        n = len(stratum)
        if n == 1:
            for cid in stratum["lineage_cluster_id"]:
                assignments[cid] = "train"
            continue
        if n == 2:
            cids = stratum["lineage_cluster_id"].tolist()
            assignments[cids[0]] = "train"
            assignments[cids[1]] = "test"
            continue

        n_train = max(1, round(n * train_frac))
        n_val = max(1, round(n * val_frac))
        n_test = n - n_train - n_val
        if n_test <= 0:
            n_test = 1
            n_train = n - n_val - n_test

        indices = list(range(n))
        third = n // 3
        for start in range(0, n, max(third, 1)):
            end = min(start + max(third, 1), n)
            block = indices[start:end]
            rng.shuffle(block)
            indices[start:end] = block

        cids = stratum.iloc[indices]["lineage_cluster_id"].tolist()
        for i, cid in enumerate(cids):
            if i < n_train:
                assignments[cid] = "train"
            elif i < n_train + n_val:
                assignments[cid] = "val"
            else:
                assignments[cid] = "test"

    cp["split"] = cp["lineage_cluster_id"].map(assignments)
    return cp


def _export_split_files(splits, samples, output_dir):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, sdf in splits.items():
        fp = out / f"{name}.jsonl"
        indices = sdf["sample_index"].tolist()
        with open(fp, "w", encoding="utf-8") as f:
            for idx in indices:
                f.write(json.dumps(samples[idx], ensure_ascii=False) + "\n")
        logger.info(f"Exported {name}: {len(indices)} samples -> {fp}")


# ════════════════════════════════════════
# CLI
# ════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Self-contained fine-tuning data pipeline")

    parser.add_argument("--step", type=str, default="all", choices=["all"] + ALL_STEPS)
    parser.add_argument("--from-step", type=str, default=None, choices=ALL_STEPS)

    parser.add_argument("--n-seeds", type=int, default=SEED_DEFAULT_COUNT)
    parser.add_argument("--domains", type=str, default=",".join(SEED_DOMAINS))
    parser.add_argument("--min-citations", type=int, default=SEED_MIN_CITATIONS)
    parser.add_argument("--per-domain-pool", type=int, default=SEED_PER_DOMAIN_POOL)
    parser.add_argument("--seed-query", type=str, default=SEED_QUERY)
    parser.add_argument("--seeds-file", type=str, default=SEEDS_FILE)

    parser.add_argument("--max-depth", type=int, default=MAX_DEPTH)
    parser.add_argument("--max-seeds", type=int, default=MAX_SEEDS_PER_RUN)
    parser.add_argument("--batch-sleep", type=float, default=BATCH_SLEEP_BETWEEN_SEEDS)

    parser.add_argument("--input", type=str, default=TRAINING_DATA_FILE)
    parser.add_argument("--repaired", type=str, default=REPAIRED_DATA_FILE)
    parser.add_argument("--splits-dir", type=str, default=SPLITS_DIR)
    parser.add_argument("--llama-dir", type=str, default=LLAMA_FORMAT_DIR)

    parser.add_argument("--train-frac", type=float, default=SPLIT_TRAIN_FRAC)
    parser.add_argument("--val-frac", type=float, default=SPLIT_VAL_FRAC)
    parser.add_argument("--test-frac", type=float, default=SPLIT_TEST_FRAC)
    parser.add_argument("--seed", type=int, default=SPLIT_RANDOM_SEED)

    parser.add_argument("--bucket", type=str, default=GCS_BUCKET_NAME)
    parser.add_argument("--project", type=str, default=GCS_PROJECT_ID)
    parser.add_argument("--gcs-prefix", type=str, default=GCS_UPLOAD_PREFIX)

    args = parser.parse_args()

    if args.from_step:
        steps = ALL_STEPS[ALL_STEPS.index(args.from_step):]
    elif args.step == "all":
        steps = ALL_STEPS
    else:
        steps = [args.step]

    logger.info(f"Running steps: {' -> '.join(steps)}")
    logger.info(f"Output dir: {RUN_DIR}")
    logger.info(f"Log file: {LOG_FILE}")

    RUN_DIR.mkdir(parents=True, exist_ok=True)

    # Validate upfront
    needs_gemini = bool({"batch_run"} & set(steps))
    needs_gcs = bool({"upload"} & set(steps))

    if needs_gemini and not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY not set. Run: set GEMINI_API_KEY=your_key")
        sys.exit(1)
    if needs_gcs:
        try:
            from google.cloud import storage  # noqa: F401
        except ImportError:
            logger.error("google-cloud-storage not installed. Run: pip install google-cloud-storage")
            sys.exit(1)

    step_runners = {
        "seed_generation": ("STEP 1: SEED GENERATION", lambda: step_seed_generation(
            args.n_seeds, args.domains, args.min_citations,
            args.per_domain_pool, args.seed_query, args.seeds_file)),
        "batch_run": ("STEP 2: BATCH LINEAGE TRACING", lambda: step_batch_run(
            args.seeds_file, args.max_depth, args.max_seeds, args.batch_sleep)),
        "preprocessing": ("STEP 3: PREPROCESSING", lambda: step_preprocessing(args.input)),
        "repair": ("STEP 4: REPAIR LINEAGE CHAINS", lambda: step_repair(args.input, args.repaired)),
        "split": ("STEP 5: STRATIFIED SPLIT", lambda: step_split(
            args.repaired, args.splits_dir, args.train_frac, args.val_frac, args.test_frac, args.seed)),
        "convert": ("STEP 6: CONVERT TO LLAMA FORMAT", lambda: step_convert(args.splits_dir, args.llama_dir)),
        "report": ("STEP 7: PIPELINE REPORT", lambda: step_report(args.repaired, args.splits_dir, args.llama_dir)),
        "upload": ("STEP 8: UPLOAD TO GCS", lambda: step_upload(args.bucket, args.project, args.gcs_prefix)),
    }

    for step_name in steps:
        label, runner = step_runners[step_name]
        logger.info(f"\n{'='*50}\n{label}\n{'='*50}")
        try:
            result = runner()
            if step_name == "batch_run" and result.get("training_examples", 0) == 0:
                logger.error("No training examples generated. Stopping pipeline.")
                sys.exit(1)
        except Exception as e:
            logger.error(f"{label} failed: {e}")
            logger.debug(traceback.format_exc())
            sys.exit(1)

    logger.info(f"\nPipeline complete! All outputs in: {RUN_DIR}")
    logger.info(f"Log file: {LOG_FILE}")


if __name__ == "__main__":
    main()