"""
evolution_view/gemini_analysis.py
----------------------------------
Gemini 2.5 Pro analysis for the evolution pipeline.
Same logic as original; updated to use common.config imports.
"""

import json
import random
import time

from google import genai
from google.genai import types

from ..common.config import (
    GEMINI_PROJECT, GEMINI_LOCATION, GEMINI_MODEL,
    GEMINI_TEMPERATURE, GEMINI_MAX_OUTPUT_TOKENS,
    VERBOSE, logger, log_event,
)
from .prompts.prompts import MAIN_PROMPT, FOUNDATIONAL_PROMPT

print = logger.info

_client = genai.Client(
    vertexai=True,
    project=GEMINI_PROJECT,
    location=GEMINI_LOCATION,
)


# ── Input construction ────────────────────────────────────────────────────────

def build_main_input(target_text, candidates_with_context, original_target_info=None):
    parts = [MAIN_PROMPT]

    if original_target_info:
        parts += [
            f"\n{'=' * 60}",
            "LINEAGE CONTEXT — READ THIS CAREFULLY",
            f"{'=' * 60}",
            f"Original paper being traced: {original_target_info.get('title', 'Unknown')}",
            f"Research domain: {original_target_info.get('domain', 'Unknown')}",
            "",
            "CRITICAL RULE: Select a predecessor in the same research domain.",
            "Trace how the TASK/PROBLEM was solved over time, not how an architecture evolved across tasks.",
            "If no candidate is in the same domain, set selected_predecessor_id to null.",
        ]

    parts += [f"\n{'=' * 60}", "TARGET PAPER", f"{'=' * 60}", target_text]
    parts += [f"\n{'=' * 60}", "CANDIDATE PREDECESSOR PAPERS", f"{'=' * 60}"]

    for i, (paper_data, text, source_type, contexts) in enumerate(candidates_with_context, 1):
        parts += [
            f"\n{'─' * 40}",
            f"CANDIDATE {i} (Paper ID: {paper_data.get('paperId', 'unknown')})",
            f"{'─' * 40}",
            text,
        ]
        if contexts:
            parts.append("\nCITATION CONTEXTS:")
            for j, ctx in enumerate(contexts[:5], 1):
                parts.append(f"  [{j}] \"{ctx}\"")

    return "\n".join(parts)


def build_foundational_input(paper_text):
    return "\n".join([
        FOUNDATIONAL_PROMPT,
        f"\n{'=' * 60}", "PAPER TO ANALYZE", f"{'=' * 60}",
        paper_text,
    ])


# ── Gemini API call ───────────────────────────────────────────────────────────

def call_gemini(prompt_text, max_retries=3):
    token_estimate = len(prompt_text) // 4
    if VERBOSE:
        cost = (min(token_estimate, 200_000) / 1_000_000) * 1.25 + (max(0, token_estimate - 200_000) / 1_000_000) * 2.50
        print(f"  Sending ~{token_estimate:,} tokens to Gemini (est. ${cost:.3f})")

    for attempt in range(max_retries):
        try:
            response = _client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt_text,
                config=types.GenerateContentConfig(
                    temperature=GEMINI_TEMPERATURE,
                    max_output_tokens=GEMINI_MAX_OUTPUT_TOKENS,
                    response_mime_type="application/json",
                    thinking_config=types.ThinkingConfig(thinking_budget=1024),
                ),
            )
            if response and response.text:
                usage = response.usage_metadata
                if usage:
                    pt = getattr(usage, "prompt_token_count", 0) or 0
                    ot = getattr(usage, "candidates_token_count", 0) or 0
                    tt = getattr(usage, "thoughts_token_count", 0) or 0
                    cost = (min(pt, 200_000) / 1_000_000) * 1.25 + (max(0, pt - 200_000) / 1_000_000) * 2.50 + (ot / 1_000_000) * 10.0
                    log_event("GEMINI_CALL", model=GEMINI_MODEL, prompt_tokens=pt,
                              thinking_tokens=tt, output_tokens=ot, cost_usd=f"{cost:.4f}")
                return response.text
            return None
        except Exception as e:
            if any(code in str(e) for code in ["503", "UNAVAILABLE", "429"]):
                wait = min(15 * (2 ** attempt), 300)
                wait += random.uniform(-wait * 0.3, wait * 0.3)
                if VERBOSE:
                    print(f"  Gemini overloaded. Waiting {int(wait)}s... ({attempt + 1}/{max_retries})")
                time.sleep(wait)
            else:
                if VERBOSE:
                    print(f"  Gemini API error: {e}")
                return None
    return None


# ── Response parsing ──────────────────────────────────────────────────────────

def parse_response(response_text):
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
    return _try_fix_json(text)


def _try_fix_json(text):
    import re
    text = re.sub(r",\s*([}\]])", r"\1", text)
    text += "]" * (text.count("[") - text.count("]"))
    text += "}" * (text.count("{") - text.count("}"))
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        if VERBOSE:
            print(f"  JSON parse error: {e}")
        return None


def validate_main_response(parsed):
    if not parsed:
        return False
    if parsed.get("selected_predecessor_id") is None:
        return True
    if not parsed.get("selected_predecessor_id"):
        return False
    ta = parsed.get("target_analysis", {})
    for field in ["problem_addressed", "core_method", "key_innovation",
                  "breakthrough_level", "explanation_eli5", "explanation_intuitive", "explanation_technical"]:
        if not ta.get(field):
            return False
    comp = parsed.get("comparison", {})
    for field in ["what_was_improved", "how_it_was_improved", "why_it_matters", "problem_solved_from_predecessor"]:
        if not comp.get(field):
            return False
    return True


def validate_foundational_response(parsed):
    if not parsed:
        return False
    ta = parsed.get("target_analysis", {})
    for field in ["problem_addressed", "core_method", "key_innovation",
                  "breakthrough_level", "explanation_eli5", "explanation_intuitive", "explanation_technical"]:
        if not ta.get(field):
            return False
    return True


# ── High-level functions (used by pipeline.py) ────────────────────────────────

def analyze_step(target_text, candidates_with_context, original_target_info=None):
    prompt = build_main_input(target_text, candidates_with_context, original_target_info)
    for _ in range(2):
        raw  = call_gemini(prompt)
        parsed = parse_response(raw)
        if validate_main_response(parsed):
            return parsed, prompt, raw
        if VERBOSE:
            print("  Gemini response validation failed. Retrying...")
    return None, None, None


def analyze_foundational(paper_text):
    prompt = build_foundational_input(paper_text)
    for _ in range(2):
        raw    = call_gemini(prompt)
        parsed = parse_response(raw)
        if validate_foundational_response(parsed):
            return parsed, prompt, raw
        if VERBOSE:
            print("  Foundational response validation failed. Retrying...")
    return None, None, None
