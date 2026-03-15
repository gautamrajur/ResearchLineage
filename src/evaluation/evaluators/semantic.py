# src/evaluation/evaluators/semantic.py
from __future__ import annotations

import logging
from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer

from src.evaluation.types import GroundTruth, SemanticScores

logger = logging.getLogger(__name__)

# Fields evaluated with semantic similarity and their extraction paths
_SEMANTIC_FIELDS: dict[str, tuple[str, list[str]]] = {
    # metric_name: (gt_attr_or_path, pred_path_list)
    "explanation_eli5": (
        "explanation_eli5",
        ["target_analysis", "explanation_eli5"],
    ),
    "explanation_intuitive": (
        "explanation_intuitive",
        ["target_analysis", "explanation_intuitive"],
    ),
    "explanation_technical": (
        "explanation_technical",
        ["target_analysis", "explanation_technical"],
    ),
    "problem_addressed": (
        "problem_addressed",
        ["target_analysis", "problem_addressed"],
    ),
    "core_method": (
        "core_method",
        ["target_analysis", "core_method"],
    ),
    "key_innovation": (
        "key_innovation",
        ["target_analysis", "key_innovation"],
    ),
}

# List fields averaged element-wise then mean-pooled
_LIST_FIELDS: dict[str, tuple[str, list[str]]] = {
    "limitations_avg": ("limitations", ["target_analysis", "limitations"]),
    "remaining_limitations_avg": (
        "remaining_limitations",
        ["comparison", "remaining_limitations"],
    ),
}


class SemanticEvaluator:
    """
    Computes cosine similarity between predicted and ground truth text fields
    using a sentence-transformers model loaded once per evaluator instance.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        logger.info("Loading sentence-transformers model", extra={"model": model_name})
        self._model = SentenceTransformer(model_name)
        logger.info("Sentence-transformers model loaded")

    def evaluate(
        self,
        prediction: dict[str, Any] | None,
        ground_truth: GroundTruth,
    ) -> SemanticScores:
        """
        Encode GT and predicted text for each field and compute cosine similarity.
        Returns scores in [0, 1]. Missing predictions score 0.0.
        """
        gt_dict = ground_truth.model_dump()
        pred_dict = prediction or {}

        scores: dict[str, float] = {}

        # --- single-text fields ---
        for metric_name, (gt_attr, pred_path) in _SEMANTIC_FIELDS.items():
            gt_text = str(gt_dict.get(gt_attr) or "")
            pred_text = _extract_nested(pred_dict, pred_path)

            scores[metric_name] = self._cosine(gt_text, pred_text)

        # --- list fields (averaged) ---
        for metric_name, (gt_attr, pred_path) in _LIST_FIELDS.items():
            gt_items = gt_dict.get(gt_attr) or []
            pred_items = _extract_nested_list(pred_dict, pred_path)

            scores[metric_name] = self._list_similarity(gt_items, pred_items)

        mean_score = float(np.mean(list(scores.values()))) if scores else 0.0

        logger.debug(
            "Semantic evaluation complete",
            extra={"mean_score": round(mean_score, 4)},
        )

        return SemanticScores(
            explanation_eli5=scores["explanation_eli5"],
            explanation_intuitive=scores["explanation_intuitive"],
            explanation_technical=scores["explanation_technical"],
            problem_addressed=scores["problem_addressed"],
            core_method=scores["core_method"],
            key_innovation=scores["key_innovation"],
            limitations_avg=scores["limitations_avg"],
            remaining_limitations_avg=scores["remaining_limitations_avg"],
            mean_score=mean_score,
        )

    def _cosine(self, text_a: str, text_b: str) -> float:
        """Cosine similarity between two strings. Returns 0.0 if either is empty."""
        if not text_a.strip() or not text_b.strip():
            return 0.0
        embs = self._model.encode([text_a, text_b], convert_to_numpy=True)
        a, b = embs[0], embs[1]
        denom = np.linalg.norm(a) * np.linalg.norm(b)
        if denom == 0:
            return 0.0
        return float(np.dot(a, b) / denom)

    def _list_similarity(
        self,
        gt_items: list[str],
        pred_items: list[str],
    ) -> float:
        """
        For each GT item, find the max cosine similarity across all pred items.
        Average over all GT items. Returns 0.0 if either list is empty.
        """
        if not gt_items or not pred_items:
            return 0.0

        gt_texts = [str(x) for x in gt_items if x]
        pred_texts = [str(x) for x in pred_items if x]

        if not gt_texts or not pred_texts:
            return 0.0

        gt_embs = self._model.encode(gt_texts, convert_to_numpy=True)
        pred_embs = self._model.encode(pred_texts, convert_to_numpy=True)

        item_scores: list[float] = []
        for gt_emb in gt_embs:
            sims = [
                float(
                    np.dot(gt_emb, p_emb)
                    / max(np.linalg.norm(gt_emb) * np.linalg.norm(p_emb), 1e-8)
                )
                for p_emb in pred_embs
            ]
            item_scores.append(max(sims))

        return float(np.mean(item_scores))


# ----------------------------------------------------------------- helpers


def _extract_nested(d: dict[str, Any], path: list[str]) -> str:
    current: Any = d
    for key in path:
        if not isinstance(current, dict):
            return ""
        current = current.get(key, "")
    return str(current) if current is not None else ""


def _extract_nested_list(d: dict[str, Any], path: list[str]) -> list[str]:
    current: Any = d
    for key in path:
        if not isinstance(current, dict):
            return []
        current = current.get(key, [])
    if isinstance(current, list):
        return [str(x) for x in current if x]
    return []
