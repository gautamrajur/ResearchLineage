# scripts/test_endpoints.py
"""
Smoke test for both the Llama inference endpoint and Gemini judge client.
Run with: poetry run python scripts/test_endpoints.py
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

PROJECT_ID = os.getenv("EVAL_GCS_PROJECT_ID", "research-lineage-eval")
VERTEX_PROJECT_ID = os.getenv("EVAL_VERTEX_PROJECT_ID") or PROJECT_ID
JUDGE_PROJECT_ID = os.getenv("EVAL_JUDGE_PROJECT_ID") or PROJECT_ID
LOCATION = os.getenv("EVAL_VERTEX_LOCATION", "us-central1")
LLAMA_ENDPOINT_ID = os.getenv("EVAL_VERTEX_ENDPOINT_ID", "")
JUDGE_MODEL_NAME = os.getenv("EVAL_JUDGE_MODEL_NAME", "gemini-2.5-flash")

TEST_PROMPT = (
    "You are an expert research analyst. "
    "In one sentence, what is the main contribution of the Transformer paper?"
)


def test_llama() -> None:
    print("\n" + "=" * 60)
    print("TESTING LLAMA 3 8B INFERENCE ENDPOINT")
    print("=" * 60)

    if not LLAMA_ENDPOINT_ID:
        print("[SKIP] EVAL_VERTEX_ENDPOINT_ID not set in .env")
        return

    from src.evaluation.model_client import build_inference_client

    client = build_inference_client(
        endpoint_id=LLAMA_ENDPOINT_ID,
        project_id=VERTEX_PROJECT_ID,
        location=LOCATION,
    )

    print(f"Endpoint ID : {LLAMA_ENDPOINT_ID}")
    print(f"Prompt      : {TEST_PROMPT}")
    print("Calling endpoint (timeout=300s)...")

    try:
        response = client.predict(TEST_PROMPT)
        print(f"\n[OK] Response received ({len(response)} chars):")
        print(response[:500])
    except Exception as exc:
        print(f"\n[FAIL] {exc}")
        sys.exit(1)


def test_gemini() -> None:
    print("\n" + "=" * 60)
    print("TESTING GEMINI JUDGE CLIENT")
    print("=" * 60)

    from src.evaluation.model_client import build_judge_client

    client = build_judge_client(
        project_id=JUDGE_PROJECT_ID,
        location=LOCATION,
        model_name=JUDGE_MODEL_NAME,
    )

    print(f"Model       : {JUDGE_MODEL_NAME}")
    print(f"Prompt      : {TEST_PROMPT}")
    print("Calling Gemini...")

    try:
        response = client.predict(TEST_PROMPT)
        print(f"\n[OK] Response received ({len(response)} chars):")
        print(response[:500])
    except Exception as exc:
        print(f"\n[FAIL] {exc}")
        sys.exit(1)


if __name__ == "__main__":
    test_gemini()
    test_llama()
    print("\n[ALL TESTS PASSED] Both endpoints are working.")
