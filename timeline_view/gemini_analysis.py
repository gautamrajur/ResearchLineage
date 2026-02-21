"""
gemini_analysis.py - Gemini 2.5 Pro analysis for timeline pipeline

Prompts are imported from prompts.py (kept separate for easy editing/versioning).
This file handles: input construction, API calls, response parsing, validation.
"""

import json
from google import genai
from google.genai import types
import random
import time

from config import (
    GEMINI_API_KEY, GEMINI_MODEL,
    GEMINI_TEMPERATURE, GEMINI_MAX_OUTPUT_TOKENS,
    VERBOSE
)
from prompts.prompts import MAIN_PROMPT, FOUNDATIONAL_PROMPT


# ========================================
# Gemini Client
# ========================================

_client = genai.Client(api_key=GEMINI_API_KEY)


# ========================================
# Input Construction
# ========================================

def build_main_input(target_text, candidates_with_context, original_target_info=None):
    """
    Build the full prompt for a regular pipeline step.

    Args:
        target_text: Formatted text of target paper
        candidates_with_context: List of tuples:
            (paper_data, formatted_text, source_type, contexts)
        original_target_info: Optional dict with original target info for domain context

    Returns:
        str: Complete prompt string
    """
    parts = [MAIN_PROMPT]

    # Add domain context if tracing deeper in the chain
    if original_target_info:
        parts.append(f"\n{'=' * 60}")
        parts.append("⚠️ LINEAGE CONTEXT — READ THIS CAREFULLY")
        parts.append(f"{'=' * 60}")
        parts.append(f"Original paper being traced: {original_target_info.get('title', 'Unknown')}")
        parts.append(f"Research domain: {original_target_info.get('domain', 'Unknown')}")
        parts.append("")
        parts.append("CRITICAL RULE: You MUST select a predecessor that is in the same research domain.")
        parts.append("The lineage should trace how the TASK/PROBLEM was solved over time, not how a neural network architecture evolved across different tasks.")
        parts.append("If the original paper is about machine translation, every predecessor must also be about machine translation, sequence-to-sequence modeling, or language modeling.")
        parts.append("Do NOT select papers from other domains (discourse analysis, speech recognition, image classification, etc.) even if they use a similar architecture.")
        parts.append("If no candidate is in the same domain, STOP and set selected_predecessor_id to null.")

    # Target paper
    parts.append(f"\n{'=' * 60}")
    parts.append("TARGET PAPER")
    parts.append(f"{'=' * 60}")
    parts.append(target_text)

    # Candidate papers
    parts.append(f"\n{'=' * 60}")
    parts.append("CANDIDATE PREDECESSOR PAPERS")
    parts.append(f"{'=' * 60}")

    for i, (paper_data, text, source_type, contexts) in enumerate(candidates_with_context, 1):
        paper_id = paper_data.get("paperId", "unknown")

        parts.append(f"\n{'─' * 40}")
        parts.append(f"CANDIDATE {i} (Paper ID: {paper_id})")
        parts.append(f"{'─' * 40}")
        parts.append(text)

        if contexts:
            parts.append(f"\nCITATION CONTEXTS (how target paper cites this paper):")
            for j, ctx in enumerate(contexts[:5], 1):
                parts.append(f"  [{j}] \"{ctx}\"")

    return "\n".join(parts)


def build_foundational_input(paper_text):
    """
    Build prompt for the foundational paper (last in chain).

    Args:
        paper_text: Formatted text of the paper

    Returns:
        str: Complete prompt string
    """
    parts = [
        FOUNDATIONAL_PROMPT,
        f"\n{'=' * 60}",
        "PAPER TO ANALYZE",
        f"{'=' * 60}",
        paper_text
    ]
    return "\n".join(parts)


# ========================================
# Gemini API Call
# ========================================

def call_gemini(prompt_text, max_retries=3):
    """
    Call Gemini 2.5 Pro and return raw response text.
    Retries on 503 (server overloaded) with exponential backoff.

    Args:
        prompt_text: Complete prompt string
        max_retries: Number of retry attempts for 503 errors

    Returns:
        str: Raw response text or None on failure
    """
    token_estimate = len(prompt_text) // 4
    if token_estimate > 200_000:
        cost = (200_000 / 1_000_000) * 1.25 + ((token_estimate - 200_000) / 1_000_000) * 2.50
    else:
        cost = (token_estimate / 1_000_000) * 1.25

    if VERBOSE:
        print(f"  📝 Sending ~{token_estimate:,} tokens to Gemini "
              f"(est. cost: ${cost:.3f})")
    
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
                )
            )

            if response and response.text:
                if VERBOSE:
                    print(f"  ✅ Gemini responded ({len(response.text)} chars)")
                return response.text
            else:
                if VERBOSE:
                    print("  ❌ Gemini returned empty response")
                return None

        except Exception as e:
            error_str = str(e)

            # Retry only for overload / rate limit
            if any(code in error_str for code in ["503", "UNAVAILABLE", "429"]):

                # Exponential backoff with jitter
                base_wait = 15  # seconds
                wait = base_wait * (2 ** attempt)

                # Add jitter (±30%)
                jitter = wait * 0.3
                wait = wait + random.uniform(-jitter, jitter)

                wait = min(wait, 300)  # cap at 5 minutes

                if VERBOSE:
                    print(
                        f"  ⚠️  Gemini overloaded. "
                        f"Waiting {int(wait)}s... "
                        f"(Attempt {attempt + 1}/{max_retries})"
                    )

                time.sleep(wait)
                continue

            # Non-retryable error
            if VERBOSE:
                print(f"  ❌ Gemini API error: {e}")
            return None

# ========================================
# Response Parsing
# ========================================

def parse_response(response_text):
    """
    Parse Gemini's JSON response.
    Handles clean JSON, markdown-wrapped JSON, extra whitespace,
    and common JSON formatting errors (trailing commas, etc.).
    """
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

    fixed = _fix_json(text)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError as e:
        if VERBOSE:
            print(f"  ❌ JSON parse error: {e}")
            print(f"  Raw response (first 500 chars): {text[:500]}")
        return None


def _fix_json(text):
    """Fix common JSON errors from LLMs."""
    import re

    # Remove trailing commas before } or ]
    text = re.sub(r',\s*([}\]])', r'\1', text)

    # Check for truncated JSON
    open_braces = text.count('{') - text.count('}')
    open_brackets = text.count('[') - text.count(']')

    if open_brackets > 0 or open_braces > 0:
        text = text.rstrip()
        if text.endswith(','):
            text = text[:-1]
        text += ']' * open_brackets
        text += '}' * open_braces

    return text


def validate_main_response(parsed):
    """Validate that a main step response has all required fields."""
    if not parsed:
        return False

    if not parsed.get("selected_predecessor_id"):
        # null predecessor is valid (domain boundary)
        if parsed.get("selected_predecessor_id") is None:
            return True
        if VERBOSE:
            print(f"  ❌ Missing selected_predecessor_id")
        return False

    analysis = parsed.get("target_analysis", {})
    for field in ["problem_addressed", "core_method", "key_innovation",
                   "breakthrough_level", "explanation_eli5",
                   "explanation_intuitive", "explanation_technical"]:
        if not analysis.get(field):
            if VERBOSE:
                print(f"  ❌ Missing target_analysis.{field}")
            return False

    comparison = parsed.get("comparison", {})
    for field in ["what_was_improved", "how_it_was_improved",
                   "why_it_matters", "problem_solved_from_predecessor"]:
        if not comparison.get(field):
            if VERBOSE:
                print(f"  ❌ Missing comparison.{field}")
            return False

    return True


def validate_foundational_response(parsed):
    """Validate that a foundational paper response has required fields."""
    if not parsed:
        return False

    analysis = parsed.get("target_analysis", {})
    for field in ["problem_addressed", "core_method", "key_innovation",
                   "breakthrough_level", "explanation_eli5",
                   "explanation_intuitive", "explanation_technical"]:
        if not analysis.get(field):
            if VERBOSE:
                print(f"  ❌ Missing target_analysis.{field}")
            return False

    return True


# ========================================
# High-Level Functions (used by pipeline.py)
# ========================================

def analyze_step(target_text, candidates_with_context, original_target_info=None):
    """
    Run one pipeline step: select predecessor + analyze + compare.

    Returns:
        tuple: (parsed_dict, prompt_text, raw_response_text) or (None, None, None)
    """
    prompt = build_main_input(target_text, candidates_with_context, original_target_info)
    response_text = call_gemini(prompt)
    parsed = parse_response(response_text)

    if not validate_main_response(parsed):
        if VERBOSE:
            print(f"  ⚠️  Response validation failed. Retrying...")
        response_text = call_gemini(prompt)
        parsed = parse_response(response_text)
        if not validate_main_response(parsed):
            if VERBOSE:
                print(f"  ❌ Retry also failed.")
            return None, None, None

    return parsed, prompt, response_text


def analyze_foundational(paper_text):
    """
    Analyze the foundational paper (last in chain, no predecessor).

    Returns:
        tuple: (parsed_dict, prompt_text, raw_response_text) or (None, None, None)
    """
    prompt = build_foundational_input(paper_text)
    response_text = call_gemini(prompt)
    parsed = parse_response(response_text)

    if not validate_foundational_response(parsed):
        if VERBOSE:
            print(f"  ⚠️  Response validation failed. Retrying...")
        response_text = call_gemini(prompt)
        parsed = parse_response(response_text)
        if not validate_foundational_response(parsed):
            if VERBOSE:
                print(f"  ❌ Retry also failed.")
            return None, None, None

    return parsed, prompt, response_text


# ========================================
# Test
# ========================================

if __name__ == "__main__":
    print("=" * 60)
    print("Testing Gemini Analysis Module")
    print("=" * 60)

    print("\n1️⃣  Testing Gemini connection...")
    test_response = call_gemini(
        "Respond with valid JSON: {\"status\": \"ok\", \"model\": \"gemini-2.5-pro\"}"
    )
    if test_response:
        parsed = parse_response(test_response)
        print(f"   Parsed: {parsed}")

    print("\n2️⃣  Testing foundational prompt build...")
    sample_text = """TITLE: Long Short-Term Memory
YEAR: 1997
PAPER_ID: test123
SOURCE: ABSTRACT_ONLY

## Abstract
Learning to store information over extended time intervals by recurrent
backpropagation takes a very long time."""

    prompt = build_foundational_input(sample_text)
    print(f"   Prompt length: {len(prompt)} chars (~{len(prompt)//4} tokens)")

    print("\n✅ Done!")