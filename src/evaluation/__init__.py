# src/evaluation/__init__.py
"""
ResearchLineage LLM Evaluation Pipeline.

Four DAG-ready entry points in src.evaluation.pipeline:
    load_eval_data   — ingest samples from GCS
    run_inference    — call fine-tuned model (Vertex, Modal JSON, or OpenAI-compatible API)
    evaluate_all     — classification + LLM judge + semantic similarity
    save_results     — write per-sample JSONL + aggregate JSON to GCS
"""
# intentionally empty — no imports here to avoid circular imports.
# import directly from submodules:
#   from src.evaluation.pipeline import load_eval_data, run_inference, ...
#   from src.evaluation.model_client import build_inference_client, ...
