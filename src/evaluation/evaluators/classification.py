# src/evaluation/evaluators/classification.py
from __future__ import annotations

import logging
from typing import Any

from src.evaluation.types import ClassificationScores, GroundTruth

logger = logging.getLogger(__name__)

_VALID_BREAKTHROUGH_LEVELS = {"revolutionary", "major", "moderate", "minor"}

_REQUIRED_TOP_KEYS = {
    "selected_predecessor_id",
    "selection_reasoning",
    "secondary_influences",
    "target_analysis",
    "comparison",
}
_REQUIRED_TARGET_ANALYSIS_KEYS = {
    "problem_addressed",
    "core_method",
    "key_innovation",
    "limitations",
    "breakthrough_level",
    "explanation_eli5",
    "explanation_intuitive",
    "explanation_technical",
}
_REQUIRED_COMPARISON_KEYS = {
    "what_was_improved",
    "how_it_was_improved",
    "why_it_matters",
    "problem_solved_from_predecessor",
    "remaining_limitations",
}


def evaluate_classification(
    prediction: dict[str, Any] | None,
    ground_truth: GroundTruth,
) -> ClassificationScores:
    """
    Compute deterministic classification metrics and schema validation.

    MRR logic for predecessor_id:
      - Score 1.0  → exact match in selected_predecessor_id
      - Score 1/2  → correct id appears at index 0 of secondary_influences
      - Score 1/3  → index 1 of secondary_influences
      - Score 0.0  → not found anywhere
    """
    schema_errors = _validate_schema(prediction)
    schema_valid = len(schema_errors) == 0

    if prediction is None:
        logger.warning("Prediction is None — returning zero classification scores.")
        return ClassificationScores(
            predecessor_id_correct=False,
            predecessor_id_soft_correct=False,
            predecessor_id_mrr=0.0,
            breakthrough_level_correct=False,
            secondary_influences_f1=0.0,
            schema_valid=False,
            schema_errors=["prediction is None"],
        )

    # ---- predecessor_id ----
    pred_predecessor = prediction.get("selected_predecessor_id")
    gt_predecessor = ground_truth.selected_predecessor_id

    predecessor_correct = pred_predecessor == gt_predecessor

    # soft: also correct if pred pick appears in GT secondary_influences
    gt_secondary_ids = {
        item.get("paper_id", "")
        for item in ground_truth.secondary_influences
        if isinstance(item, dict)
    }
    predecessor_soft_correct = predecessor_correct or (
        pred_predecessor is not None and pred_predecessor in gt_secondary_ids
    )

    mrr = _compute_predecessor_mrr(prediction, gt_predecessor)

    # ---- breakthrough_level ----
    pred_level = (
        prediction.get("target_analysis", {}).get("breakthrough_level", "").lower()
    )
    gt_level = ground_truth.breakthrough_level.lower()
    breakthrough_correct = pred_level == gt_level

    # ---- secondary_influences F1 ----
    pred_influences = {
        item.get("paper_id", "")
        for item in prediction.get("secondary_influences", [])
        if isinstance(item, dict)
    }
    gt_influences = {
        item.get("paper_id", "")
        for item in ground_truth.secondary_influences
        if isinstance(item, dict)
    }
    influences_f1 = _f1(pred_influences, gt_influences)

    logger.debug(
        "Classification evaluation complete",
        extra={
            "predecessor_correct": predecessor_correct,
            "predecessor_soft_correct": predecessor_soft_correct,
            "mrr": mrr,
            "breakthrough_correct": breakthrough_correct,
            "influences_f1": round(influences_f1, 4),
            "schema_valid": schema_valid,
        },
    )

    return ClassificationScores(
        predecessor_id_correct=predecessor_correct,
        predecessor_id_soft_correct=predecessor_soft_correct,
        predecessor_id_mrr=mrr,
        breakthrough_level_correct=breakthrough_correct,
        secondary_influences_f1=influences_f1,
        schema_valid=schema_valid,
        schema_errors=schema_errors,
    )


# ----------------------------------------------------------------- helpers


def _compute_predecessor_mrr(
    prediction: dict[str, Any],
    gt_predecessor: str | None,
) -> float:
    if gt_predecessor is None:
        # ground truth has null predecessor — correct only if prediction also null
        return 1.0 if prediction.get("selected_predecessor_id") is None else 0.0

    if prediction.get("selected_predecessor_id") == gt_predecessor:
        return 1.0

    secondary = prediction.get("secondary_influences", [])
    for rank, item in enumerate(secondary, start=2):
        if isinstance(item, dict) and item.get("paper_id") == gt_predecessor:
            return 1.0 / rank

    return 0.0


def _f1(pred: set[str], gt: set[str]) -> float:
    if not pred and not gt:
        return 1.0
    if not pred or not gt:
        return 0.0
    tp = len(pred & gt)
    precision = tp / len(pred)
    recall = tp / len(gt)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _validate_schema(prediction: dict[str, Any] | None) -> list[str]:
    """Return a list of schema violation strings. Empty list means valid."""
    errors: list[str] = []

    if prediction is None:
        return ["prediction is None"]

    if not isinstance(prediction, dict):
        return [f"prediction is not a dict: {type(prediction)}"]

    # top-level keys
    missing_top = _REQUIRED_TOP_KEYS - prediction.keys()
    for key in missing_top:
        errors.append(f"missing top-level key: '{key}'")

    # target_analysis sub-keys
    ta = prediction.get("target_analysis", {})
    if isinstance(ta, dict):
        missing_ta = _REQUIRED_TARGET_ANALYSIS_KEYS - ta.keys()
        for key in missing_ta:
            errors.append(f"missing target_analysis key: '{key}'")

        # breakthrough_level value check
        bl = ta.get("breakthrough_level", "")
        if bl and bl.lower() not in _VALID_BREAKTHROUGH_LEVELS:
            errors.append(
                f"invalid breakthrough_level: '{bl}'. "
                f"Expected one of {_VALID_BREAKTHROUGH_LEVELS}"
            )

        # limitations must be a non-empty list
        limitations = ta.get("limitations", [])
        if not isinstance(limitations, list) or len(limitations) == 0:
            errors.append("target_analysis.limitations must be a non-empty list")
    else:
        errors.append("target_analysis is not a dict")

    # comparison sub-keys
    comp = prediction.get("comparison", {})
    if isinstance(comp, dict):
        missing_comp = _REQUIRED_COMPARISON_KEYS - comp.keys()
        for key in missing_comp:
            errors.append(f"missing comparison key: '{key}'")

        remaining = comp.get("remaining_limitations", [])
        if not isinstance(remaining, list) or len(remaining) == 0:
            errors.append("comparison.remaining_limitations must be a non-empty list")
    else:
        errors.append("comparison is not a dict")

    # secondary_influences must be a list of dicts with paper_id
    influences = prediction.get("secondary_influences", [])
    if not isinstance(influences, list):
        errors.append("secondary_influences must be a list")
    else:
        for i, item in enumerate(influences):
            if not isinstance(item, dict) or "paper_id" not in item:
                errors.append(f"secondary_influences[{i}] missing 'paper_id'")

    return errors
