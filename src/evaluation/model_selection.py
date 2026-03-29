"""Model selection: compare evaluation reports and pick the best model.

Selection formula: Score = 0.75 * predecessor_soft + (judge_overall / 5) * 0.25
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def compute_composite_score(report: dict) -> float:
    """Compute the composite score from an aggregate evaluation report.

    Score = 0.75 * predecessor_soft + (judge_overall / 5) * 0.25
    Gives a normalized score out of 1.
    """
    cls = report.get("overall_classification", {})
    judge = report.get("overall_judge", {})
    predecessor_soft = cls.get("predecessor_soft", 0.0) or 0.0
    judge_overall = judge.get("judge_overall", 0.0) or 0.0
    return 0.75 * predecessor_soft + (judge_overall / 5.0) * 0.25


def extract_model_metrics(report: dict) -> dict[str, float]:
    """Extract key metrics from a report for comparison."""
    cls = report.get("overall_classification", {})
    judge = report.get("overall_judge", {})
    return {
        "composite": compute_composite_score(report),
        "predecessor_strict": cls.get("predecessor_strict", 0.0) or 0.0,
        "predecessor_soft": cls.get("predecessor_soft", 0.0) or 0.0,
        "mrr": cls.get("mrr", 0.0) or 0.0,
        "breakthrough": cls.get("breakthrough", 0.0) or 0.0,
        "secondary_f1": cls.get("secondary_f1", 0.0) or 0.0,
        "schema_valid": cls.get("schema_valid", 0.0) or 0.0,
        "judge_overall": judge.get("judge_overall", 0.0) or 0.0,
        "judge_selection_reasoning": judge.get("judge_selection_reasoning", 0.0) or 0.0,
        "judge_what_was_improved": judge.get("judge_what_was_improved", 0.0) or 0.0,
        "judge_how_it_was_improved": judge.get("judge_how_it_was_improved", 0.0) or 0.0,
        "judge_why_it_matters": judge.get("judge_why_it_matters", 0.0) or 0.0,
        "judge_problem_solved": judge.get("judge_problem_solved", 0.0) or 0.0,
    }


def select_best_model(reports: dict[str, dict]) -> dict[str, Any]:
    """Compare N models and return selection result.

    Args:
        reports: {model_name: aggregate_report_dict}

    Returns:
        Selection result with winner, per-model scores, rankings, and full reports.
    """
    scores: dict[str, dict[str, float]] = {}
    for name, report in reports.items():
        scores[name] = extract_model_metrics(report)

    rankings = sorted(scores.items(), key=lambda x: x[1]["composite"], reverse=True)
    winner = rankings[0][0]

    logger.info(
        "Model selection complete: winner=%s (score=%.4f)",
        winner,
        rankings[0][1]["composite"],
    )
    for rank, (name, metrics) in enumerate(rankings, 1):
        logger.info(
            "  #%d %s: composite=%.4f predecessor_soft=%.4f judge_overall=%.4f",
            rank, name, metrics["composite"], metrics["predecessor_soft"], metrics["judge_overall"],
        )

    return {
        "winner": winner,
        "selection_formula": "0.75 * predecessor_soft + (judge_overall / 5) * 0.25",
        "scores": scores,
        "rankings": [(name, metrics["composite"]) for name, metrics in rankings],
        "reports": reports,
    }


def load_reports_from_dirs(
    report_dirs: list[str],
    model_names: list[str],
) -> dict[str, dict]:
    """Load aggregate_report.json from each directory, keyed by model name."""
    reports = {}
    for dir_path, name in zip(report_dirs, model_names):
        report_path = Path(dir_path) / "aggregate_report.json"
        if not report_path.exists():
            raise FileNotFoundError(f"Report not found: {report_path}")
        reports[name] = json.loads(report_path.read_text())
        logger.info("Loaded report for %s from %s", name, report_path)
    return reports
