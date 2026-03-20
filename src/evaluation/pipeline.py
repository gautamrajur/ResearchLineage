# src/evaluation/pipeline.py
"""
Four DAG-ready functions for the LLM evaluation pipeline.

Usage in an Airflow DAG:
    from src.evaluation.pipeline import (
        load_eval_data,
        run_inference,
        evaluate_all,
        save_results,
    )
"""
from __future__ import annotations

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

import numpy as np

from src.evaluation.config import EvaluationConfig
from src.evaluation.evaluators.classification import evaluate_classification
from src.evaluation.evaluators.llm_judge import evaluate_llm_judge
from src.evaluation.evaluators.semantic import SemanticEvaluator
from src.evaluation.gcs_utils import (
    load_jsonl_from_gcs,
    save_json_to_gcs,
    save_jsonl_to_gcs,
)
from src.evaluation.model_client import build_inference_client, build_judge_client
from src.evaluation.types import (
    AggregateMetrics,
    EvalReport,
    EvalSample,
    GroundTruth,
    InferenceResult,
    SampleEvalResult,
)

logger = logging.getLogger(__name__)


# ================================================================== 1. Load


def load_eval_data(config: EvaluationConfig) -> list[EvalSample]:
    """
    Load and validate evaluation samples from GCS.

    Expected JSONL format per line:
        {
          "sample_id": "...",
          "input_text": "...",
          "ground_truth": { ...GroundTruth fields... }
        }

    Returns a list of validated EvalSample objects.
    """
    logger.info(
        "Loading evaluation data",
        extra={"gcs_input_path": config.gcs_input_path},
    )

    raw_records = load_jsonl_from_gcs(
        gcs_uri=config.gcs_input_path,
        project_id=config.gcs_project_id,
    )

    samples: list[EvalSample] = []
    parse_errors = 0

    for i, record in enumerate(raw_records):
        try:
            gt_raw = record.get("ground_truth", {})
            if isinstance(gt_raw, str):
                gt_raw = json.loads(gt_raw)

            gt_flat = _flatten_ground_truth(gt_raw)
            ground_truth = GroundTruth(**gt_flat)

            samples.append(
                EvalSample(
                    sample_id=record.get("sample_id", f"sample_{i}"),
                    input_text=record["input_text"],
                    ground_truth=ground_truth,
                )
            )
        except Exception as exc:
            parse_errors += 1
            logger.warning(
                "Failed to parse eval sample",
                extra={"index": i, "error": str(exc)},
            )

    logger.info(
        "Eval data loaded",
        extra={"n_samples": len(samples), "n_parse_errors": parse_errors},
    )
    return samples


# ================================================================== 2. Infer


def run_inference(
    samples: list[EvalSample],
    config: EvaluationConfig,
) -> list[InferenceResult]:
    """
    Run the inference model on all samples.
    Uses ModalClient (Qwen2.5 on Modal) if MODAL_ENDPOINT_URL is set,
    otherwise falls back to VertexAIClient.
    Concurrent via ThreadPoolExecutor — respects config.max_workers.
    """
    client = build_inference_client(
        endpoint_id=config.vertex_endpoint_id,
        project_id=config.vertex_project_id or config.gcs_project_id,
        location=config.vertex_location,
        modal_endpoint_url=getattr(config, "modal_endpoint_url", None),
    )

    logger.info(
        "Starting inference",
        extra={
            "n_samples": len(samples),
            "client": type(client).__name__,
            "max_workers": config.max_workers,
        },
    )

    results: list[InferenceResult] = []
    MAX_INPUT_CHARS = 32_000

    def _infer_one(sample: EvalSample) -> InferenceResult:
        start = time.monotonic()
        try:
            input_text = sample.input_text[:MAX_INPUT_CHARS]
            raw = client.predict(input_text)
            print(f"DEBUG RAW OUTPUT (full len={len(raw)}):\n{raw}")
            latency_ms = (time.monotonic() - start) * 1000
            parsed, parse_error = _parse_model_output(raw)
            return InferenceResult(
                sample_id=sample.sample_id,
                raw_output=raw,
                parsed_output=parsed,
                parse_error=parse_error,
                latency_ms=latency_ms,
            )
        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            logger.error(
                "Inference failed for sample",
                extra={"sample_id": sample.sample_id, "error": str(exc)},
            )
            return InferenceResult(
                sample_id=sample.sample_id,
                raw_output="",
                parsed_output=None,
                parse_error=str(exc),
                latency_ms=latency_ms,
            )

    with ThreadPoolExecutor(max_workers=config.max_workers) as executor:
        futures = {executor.submit(_infer_one, s): s.sample_id for s in samples}
        for future in as_completed(futures):
            results.append(future.result())

    n_errors = sum(1 for r in results if r.parse_error)
    logger.info(
        "Inference complete",
        extra={"n_results": len(results), "n_errors": n_errors},
    )
    return results


# ================================================================== 3. Evaluate


def evaluate_all(
    samples: list[EvalSample],
    inference_results: list[InferenceResult],
    config: EvaluationConfig,
) -> list[SampleEvalResult]:
    """
    Run all three evaluators (classification, LLM judge, semantic) for each sample.
    Returns per-sample results — not yet written to GCS.
    """
    run_id = config.run_id or _generate_run_id()

    judge_client = build_judge_client(
        project_id=config.judge_project_id or config.gcs_project_id,
        location=config.judge_location,
        model_name=config.judge_model_name,
        max_output_tokens=config.judge_max_output_tokens,
        temperature=config.judge_temperature,
        endpoint_id=config.judge_endpoint_id if config.judge_endpoint_id else None,
    )
    semantic_evaluator = SemanticEvaluator(model_name=config.semantic_model_name)

    inference_map: dict[str, InferenceResult] = {
        r.sample_id: r for r in inference_results
    }

    eval_results: list[SampleEvalResult] = []
    total_samples = len(samples)
    stage_start = time.monotonic()
    completed_count = 0

    def _evaluate_one(
        sample: EvalSample,
        infer: InferenceResult,
        sample_index: int,
    ) -> SampleEvalResult:
        nonlocal completed_count

        eval_errors: list[str] = []
        classification_scores = None
        judge_scores = None
        semantic_scores = None

        # -- classification --
        t0 = time.monotonic()
        try:
            classification_scores = evaluate_classification(
                prediction=infer.parsed_output,
                ground_truth=sample.ground_truth,
            )
            logger.debug(
                "Classification complete",
                extra={
                    "sample_id": sample.sample_id,
                    "latency_ms": round((time.monotonic() - t0) * 1000, 1),
                },
            )
        except Exception as exc:
            msg = f"classification evaluator error: {exc}"
            eval_errors.append(msg)
            logger.error(msg, extra={"sample_id": sample.sample_id})

        # -- llm judge --
        t0 = time.monotonic()
        try:
            judge_scores = evaluate_llm_judge(
                prediction=infer.parsed_output,
                ground_truth=sample.ground_truth,
                judge_client=judge_client,
                judge_model_id=config.judge_endpoint_id or config.judge_model_name,
                sample_id=sample.sample_id,
                sample_index=sample_index,
                total_samples=total_samples,
            )
            logger.debug(
                "LLM judge complete",
                extra={
                    "sample_id": sample.sample_id,
                    "latency_ms": round((time.monotonic() - t0) * 1000, 1),
                },
            )
        except Exception as exc:
            msg = f"llm judge evaluator error: {exc}"
            eval_errors.append(msg)
            logger.error(msg, extra={"sample_id": sample.sample_id})

        # -- semantic --
        t0 = time.monotonic()
        try:
            semantic_scores = semantic_evaluator.evaluate(
                prediction=infer.parsed_output,
                ground_truth=sample.ground_truth,
            )
            logger.debug(
                "Semantic evaluation complete",
                extra={
                    "sample_id": sample.sample_id,
                    "latency_ms": round((time.monotonic() - t0) * 1000, 1),
                },
            )
        except Exception as exc:
            msg = f"semantic evaluator error: {exc}"
            eval_errors.append(msg)
            logger.error(msg, extra={"sample_id": sample.sample_id})

        # progress counter — thread-safe increment
        completed_count += 1
        elapsed = time.monotonic() - stage_start
        avg = elapsed / completed_count
        eta = avg * (total_samples - completed_count)
        logger.info(
            f"Sample evaluated {completed_count}/{total_samples}",
            extra={
                "sample_id": sample.sample_id,
                "elapsed_s": round(elapsed, 1),
                "eta_s": round(eta, 1),
                "parse_error": bool(infer.parse_error),
            },
        )

        return SampleEvalResult(
            sample_id=sample.sample_id,
            run_id=run_id,
            input_text=sample.input_text,
            ground_truth=sample.ground_truth,
            raw_prediction=infer.raw_output,
            parsed_prediction=infer.parsed_output,
            parse_error=infer.parse_error,
            latency_ms=infer.latency_ms,
            classification=classification_scores,
            llm_judge=judge_scores,
            semantic=semantic_scores,
            eval_errors=eval_errors,
        )

    # build work list — skip samples with no inference result
    work = []
    for idx, sample in enumerate(samples, start=1):
        infer = inference_map.get(sample.sample_id)
        if infer is None:
            logger.warning(
                "No inference result for sample",
                extra={"sample_id": sample.sample_id},
            )
            continue
        work.append((sample, infer, idx))

    with ThreadPoolExecutor(max_workers=config.max_workers) as executor:
        futures = {
            executor.submit(_evaluate_one, s, inf, idx): s.sample_id
            for s, inf, idx in work
        }
        for future in as_completed(futures):
            try:
                eval_results.append(future.result())
            except Exception as exc:
                sid = futures[future]
                logger.error(
                    "Evaluation failed for sample",
                    extra={"sample_id": sid, "error": str(exc)},
                )

    logger.info(
        "Evaluation complete",
        extra={"n_evaluated": len(eval_results)},
    )
    return eval_results


# ================================================================== 4. Save


def save_results(
    eval_results: list[SampleEvalResult],
    config: EvaluationConfig,
) -> EvalReport:
    """
    Compute aggregate metrics and write two files to GCS:
      - <output_path>/run_<run_id>/per_sample_results.jsonl
      - <output_path>/run_<run_id>/aggregate_report.json
    Returns the EvalReport.
    """
    if not eval_results:
        raise ValueError("No evaluation results to save.")

    run_id = eval_results[0].run_id
    base_path = config.gcs_output_path.rstrip("/")
    run_path = f"{base_path}/run_{run_id}"
    per_sample_uri = f"{run_path}/per_sample_results.jsonl"
    aggregate_uri = f"{run_path}/aggregate_report.json"

    per_sample_records = [json.loads(r.model_dump_json()) for r in eval_results]
    save_jsonl_to_gcs(
        records=per_sample_records,
        gcs_uri=per_sample_uri,
        project_id=config.gcs_project_id,
    )

    aggregate = _compute_aggregate(eval_results)

    report = EvalReport(
        run_id=run_id,
        config_snapshot=config.model_dump(),
        aggregate=aggregate,
        per_sample_gcs_path=per_sample_uri,
    )

    save_json_to_gcs(
        data=json.loads(report.model_dump_json()),
        gcs_uri=aggregate_uri,
        project_id=config.gcs_project_id,
    )

    logger.info(
        "Results saved to GCS",
        extra={
            "run_id": run_id,
            "per_sample_uri": per_sample_uri,
            "aggregate_uri": aggregate_uri,
            "predecessor_accuracy": aggregate.predecessor_accuracy,
            "judge_overall_mean": aggregate.judge_overall_mean,
            "semantic_overall_mean": aggregate.semantic_overall_mean,
        },
    )
    return report


# ================================================================== helpers


def _flatten_ground_truth(gt: dict[str, Any]) -> dict[str, Any]:
    """
    Flatten the nested ground truth JSON (as produced by Gemini)
    into the flat structure expected by GroundTruth.
    """
    ta = gt.get("target_analysis", {})
    comp = gt.get("comparison", {})
    return {
        "selected_predecessor_id": gt.get("selected_predecessor_id"),
        "selection_reasoning": gt.get("selection_reasoning", ""),
        "secondary_influences": gt.get("secondary_influences", []),
        "problem_addressed": ta.get("problem_addressed", ""),
        "core_method": ta.get("core_method", ""),
        "key_innovation": ta.get("key_innovation", ""),
        "limitations": ta.get("limitations", []),
        "breakthrough_level": ta.get("breakthrough_level", ""),
        "explanation_eli5": ta.get("explanation_eli5", ""),
        "explanation_intuitive": ta.get("explanation_intuitive", ""),
        "explanation_technical": ta.get("explanation_technical", ""),
        "what_was_improved": comp.get("what_was_improved", ""),
        "how_it_was_improved": comp.get("how_it_was_improved", ""),
        "why_it_matters": comp.get("why_it_matters", ""),
        "problem_solved_from_predecessor": comp.get("problem_solved_from_predecessor", ""),
        "remaining_limitations": comp.get("remaining_limitations", []),
    }


def _parse_model_output(raw: str) -> tuple[dict[str, Any] | None, str | None]:
    """
    Try to extract and parse JSON from the model's raw string output.
    Handles:
    - ```json ... ``` fences (closing fence optional for truncated responses)
    - Missing commas between object fields (Qwen occasionally omits them)
    - Partial responses missing top-level fields
    Returns (parsed_dict, None) on success, (None, error_msg) on failure.
    """
    cleaned = raw.strip()

    # strip ```json ... ``` fences (closing fence optional)
    fence = re.search(r"```(?:json)?\s*([\s\S]+?)(?:```|$)", cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    else:
        brace = re.search(r"\{[\s\S]+\}", cleaned)
        if brace:
            cleaned = brace.group(0)

    # fix missing commas between fields — only before JSON keys (key: pattern)
    cleaned = re.sub(
        r'(["\d\]}\w])\s*\n(\s*"(?:[^"\\]|\\.)*"\s*:)',
        r'\1,\n\2',
        cleaned,
    )

    try:
        parsed = json.loads(cleaned)
        return _normalize_prediction(parsed), None
    except json.JSONDecodeError as exc:
        # second attempt: more aggressive comma insertion
        cleaned2 = re.sub(
            r'(["\d\]}])\s*\n(\s*")',
            r'\1,\n\2',
            cleaned,
        )
        try:
            parsed = json.loads(cleaned2)
            return _normalize_prediction(parsed), None
        except json.JSONDecodeError:
            print(f"DEBUG PARSE ERROR: {exc}")
            print(f"DEBUG CLEANED[:200]: {cleaned[:200]}")
            return None, f"JSON parse error: {exc} | raw[:200]: {raw[:200]}"


def _normalize_prediction(pred: dict[str, Any]) -> dict[str, Any]:
    """
    Fill in missing top-level fields with safe defaults so downstream
    evaluators never receive a KeyError on expected structure.
    Handles partial responses that only return target_analysis or comparison.
    """
    pred.setdefault("selected_predecessor_id", None)
    pred.setdefault("selection_reasoning", "")
    pred.setdefault("secondary_influences", [])

    ta = pred.setdefault("target_analysis", {})
    ta.setdefault("problem_addressed", "")
    ta.setdefault("core_method", "")
    ta.setdefault("key_innovation", "")
    ta.setdefault("limitations", [])
    ta.setdefault("breakthrough_level", "")
    ta.setdefault("explanation_eli5", "")
    ta.setdefault("explanation_intuitive", "")
    ta.setdefault("explanation_technical", "")

    comp = pred.setdefault("comparison", {})
    comp.setdefault("what_was_improved", "")
    comp.setdefault("how_it_was_improved", "")
    comp.setdefault("why_it_matters", "")
    comp.setdefault("problem_solved_from_predecessor", "")
    comp.setdefault("remaining_limitations", [])

    return pred


def _safe_mean(values: list[float]) -> float:
    return float(np.mean(values)) if values else 0.0


def _compute_aggregate(results: list[SampleEvalResult]) -> AggregateMetrics:
    n = len(results)
    n_parse_errors = sum(1 for r in results if r.parse_error)
    n_schema_errors = sum(
        1 for r in results
        if r.classification and not r.classification.schema_valid
    )

    def _cls(attr: str) -> list[float]:
        return [
            float(getattr(r.classification, attr))
            for r in results if r.classification is not None
        ]

    def _judge(field: str) -> list[float]:
        out = []
        for r in results:
            if r.llm_judge is None:
                continue
            score_obj = getattr(r.llm_judge, field, None)
            if score_obj is not None:
                out.append(score_obj.score)
        return out

    def _sem(attr: str) -> list[float]:
        return [
            float(getattr(r.semantic, attr))
            for r in results if r.semantic is not None
        ]

    judge_fields = [
        "selection_reasoning",
        "what_was_improved",
        "how_it_was_improved",
        "why_it_matters",
        "problem_solved_from_predecessor",
    ]
    all_judge_scores = [s for f in judge_fields for s in _judge(f)]

    return AggregateMetrics(
        n_samples=n,
        n_parse_errors=n_parse_errors,
        n_schema_errors=n_schema_errors,
        predecessor_accuracy=_safe_mean(_cls("predecessor_id_correct")),
        predecessor_mrr=_safe_mean(_cls("predecessor_id_mrr")),
        breakthrough_level_accuracy=_safe_mean(_cls("breakthrough_level_correct")),
        secondary_influences_f1_mean=_safe_mean(_cls("secondary_influences_f1")),
        judge_selection_reasoning_mean=_safe_mean(_judge("selection_reasoning")),
        judge_what_was_improved_mean=_safe_mean(_judge("what_was_improved")),
        judge_how_it_was_improved_mean=_safe_mean(_judge("how_it_was_improved")),
        judge_why_it_matters_mean=_safe_mean(_judge("why_it_matters")),
        judge_problem_solved_mean=_safe_mean(_judge("problem_solved_from_predecessor")),
        judge_overall_mean=_safe_mean(all_judge_scores),
        semantic_eli5_mean=_safe_mean(_sem("explanation_eli5")),
        semantic_intuitive_mean=_safe_mean(_sem("explanation_intuitive")),
        semantic_technical_mean=_safe_mean(_sem("explanation_technical")),
        semantic_overall_mean=_safe_mean(_sem("mean_score")),
    )


def _generate_run_id() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")