# scripts/debug_inference.py
"""
Debug script to see exactly what Llama returns for a simple JSON prompt.
Run with: poetry run python scripts/debug_inference.py
"""
import os

from dotenv import load_dotenv

from src.evaluation.model_client import build_inference_client

load_dotenv()

endpoint_id: str = os.getenv("EVAL_VERTEX_ENDPOINT_ID") or ""
project_id: str = os.getenv("EVAL_GCS_PROJECT_ID") or ""
location: str = os.getenv("EVAL_VERTEX_LOCATION") or "us-central1"

client = build_inference_client(
    endpoint_id=endpoint_id,
    project_id=project_id,
    location=location,
)

prompt = 'Respond with this exact JSON only, no other text: {"test": true}'

print("Sending prompt...")
response = client.predict(prompt)

print(f"\nLength: {len(response)}")
print("\nFirst 1000 chars:")
print(response[:1000])
print("\nRepr of first 500 chars:")
print(repr(response[:500]))
