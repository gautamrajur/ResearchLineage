# scripts/debug_pipeline.py
"""
Debugs exactly what happens during inference and judge for one sample.
Run with: poetry run python scripts/debug_pipeline.py
"""
import os

from dotenv import load_dotenv

from src.evaluation.config import EvaluationConfig
from src.evaluation.model_client import (
    GeminiClient,
    VertexAIClient,
    build_inference_client,
    build_judge_client,
)
from src.evaluation.pipeline import _parse_model_output, load_eval_data

load_dotenv()

PROJECT_ID: str = os.getenv("EVAL_GCS_PROJECT_ID") or "research-lineage-eval"
LOCATION: str = os.getenv("EVAL_VERTEX_LOCATION") or "us-central1"
ENDPOINT_ID: str = os.getenv("EVAL_VERTEX_ENDPOINT_ID") or ""
JUDGE_MODEL: str = os.getenv("EVAL_JUDGE_MODEL_NAME") or "gemini-2.5-flash"
JUDGE_ENDPOINT: str = os.getenv("EVAL_JUDGE_ENDPOINT_ID") or ""

print("=" * 60)
print("CONFIG CHECK")
print("=" * 60)
print(f"PROJECT_ID     : {PROJECT_ID}")
print(f"LOCATION       : {LOCATION}")
print(f"ENDPOINT_ID    : {ENDPOINT_ID}")
print(f"JUDGE_MODEL    : {JUDGE_MODEL}")
print(f"JUDGE_ENDPOINT : '{JUDGE_ENDPOINT}' (should be empty)")

# ---------------------------------------------------------------- step 1: inference client
print("\n" + "=" * 60)
print("STEP 1: INFERENCE CLIENT")
print("=" * 60)

inference_client = build_inference_client(
    endpoint_id=ENDPOINT_ID,
    project_id=PROJECT_ID,
    location=LOCATION,
)

short_prompt = (
    "Respond ONLY with valid JSON, no other text:\n"
    '{"selected_predecessor_id": "abc123", "selection_reasoning": "test"}'
)

try:
    raw = inference_client.predict(short_prompt)
    print(f"[OK] Short prompt response length: {len(raw)}")
    print(f"Response: {raw[:200]}")
    parsed, err = _parse_model_output(raw)
    if parsed is not None:
        print(f"Parse: OK — keys: {list(parsed.keys())}")
    else:
        print(f"Parse: FAILED — {err}")
except Exception as exc:
    print(f"[FAIL] {type(exc).__name__}: {exc}")

# ---------------------------------------------------------------- step 2: judge client
print("\n" + "=" * 60)
print("STEP 2: JUDGE CLIENT")
print("=" * 60)

judge_client = build_judge_client(
    project_id=PROJECT_ID,
    location=LOCATION,
    model_name=JUDGE_MODEL,
    endpoint_id=JUDGE_ENDPOINT if JUDGE_ENDPOINT else None,
)

print(f"Judge client type: {type(judge_client).__name__}")
if isinstance(judge_client, VertexAIClient):
    print("[WARN] Still using VertexAIClient — check EVAL_JUDGE_ENDPOINT_ID in .env")
elif isinstance(judge_client, GeminiClient):
    print("[OK] Using GeminiClient")
    try:
        response = judge_client.predict("Say hello in one word.")
        print(f"[OK] Judge response: {response[:100]}")
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}")

# ---------------------------------------------------------------- step 3: real sample
print("\n" + "=" * 60)
print("STEP 3: REAL SAMPLE INFERENCE")
print("=" * 60)

cfg = EvaluationConfig()
samples = load_eval_data(cfg)
sample = samples[0]

print(f"Sample ID     : {sample.sample_id}")
print(f"Input length  : {len(sample.input_text)} chars")

MAX_CHARS = 24000
truncated = sample.input_text[:MAX_CHARS]
print(f"Truncated to  : {len(truncated)} chars")
print("\nSending to model...")

try:
    raw = inference_client.predict(truncated)
    print(f"\n[OK] Raw response length: {len(raw)}")
    print("\nFirst 500 chars:")
    print(raw[:500])
    print("\nLast 200 chars:")
    print(raw[-200:])

    parsed, err = _parse_model_output(raw)
    if parsed is not None:
        print(f"\nParse: OK — keys: {list(parsed.keys())}")
    else:
        print(f"\nParse: FAILED — {err}")
except Exception as exc:
    print(f"[FAIL] {type(exc).__name__}: {exc}")
