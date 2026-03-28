# src/evaluation/types.py
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ================================================================== Input types


class GroundTruth(BaseModel):
    """Ground truth output from Gemini 2.5 Flash (the reference)."""

    selected_predecessor_id: str | None
    selection_reasoning: str
    secondary_influences: list[dict[str, str]]

    # target_analysis
    problem_addressed: str
    core_method: str
    key_innovation: str
    limitations: list[str]
    breakthrough_level: str
    explanation_eli5: str
    explanation_intuitive: str
    explanation_technical: str

    # comparison — empty for foundation papers (no predecessor)
    what_was_improved: str
    how_it_was_improved: str
    why_it_matters: str
    problem_solved_from_predecessor: str
    remaining_limitations: list[str]


class EvalSample(BaseModel):
    """One row of the evaluation dataset loaded from GCS."""

    sample_id: str
    input_text: str = Field(description="The full prompt sent to the model.")
    ground_truth: GroundTruth


# ================================================================= Output types


class InferenceResult(BaseModel):
    """Raw output from the model under evaluation for one sample."""

    sample_id: str
    raw_output: str
    parsed_output: dict[str, Any] | None = None
    parse_error: str | None = None
    latency_ms: float = 0.0


# ============================================================== Evaluator scores


class ClassificationScores(BaseModel):
    """Scores for fields that have a definite correct answer."""

    predecessor_id_correct: bool
    predecessor_id_soft_correct: bool = Field(
        description="True if pred matches GT top-1 OR appears in GT secondary_influences.",
    )
    predecessor_id_mrr: float = Field(
        description="MRR based on position in secondary_influences if not exact match.",
        ge=0.0,
        le=1.0,
    )
    breakthrough_level_correct: bool
    secondary_influences_f1: float = Field(ge=0.0, le=1.0)
    schema_valid: bool
    schema_errors: list[str] = Field(default_factory=list)
    is_foundation_paper: bool = Field(
        default=False,
        description="True when ground truth has no predecessor (selected_predecessor_id=null).",
    )


class JudgeScore(BaseModel):
    """Score for one field evaluated by the LLM judge."""

    field_name: str
    score: float = Field(ge=-1.0, le=5.0)
    reasoning: str = Field(description="The judge's full reasoning — stored verbatim.")
    rubric_axes: dict[str, float] = Field(
        description="Per-axis scores: factual_grounding, logical_coherence, "
        "domain_consistency, specificity.",
        default_factory=dict,
    )


class LLMJudgeScores(BaseModel):
    """
    All LLM-as-judge scores for one sample.
    Comparison fields are None for foundation papers (no predecessor)
    since ground truth is empty — including them would unfairly skew scores.
    """

    selection_reasoning: JudgeScore
    # comparison fields — None when skip_comparison=True (foundation papers)
    what_was_improved: JudgeScore | None = None
    how_it_was_improved: JudgeScore | None = None
    why_it_matters: JudgeScore | None = None
    problem_solved_from_predecessor: JudgeScore | None = None
    judge_model_id: str


class SemanticScores(BaseModel):
    """BERTScore-style cosine similarity against ground truth for free-text fields."""

    explanation_eli5: float = Field(ge=0.0, le=1.0)
    explanation_intuitive: float = Field(ge=0.0, le=1.0)
    explanation_technical: float = Field(ge=0.0, le=1.0)
    problem_addressed: float = Field(ge=0.0, le=1.0)
    core_method: float = Field(ge=0.0, le=1.0)
    key_innovation: float = Field(ge=0.0, le=1.0)
    limitations_avg: float = Field(ge=0.0, le=1.0)
    remaining_limitations_avg: float = Field(ge=0.0, le=1.0)
    mean_score: float = Field(ge=0.0, le=1.0)


# ============================================================== Per-sample result


class SampleEvalResult(BaseModel):
    """Complete evaluation record for one sample — written as one JSONL line."""

    sample_id: str
    run_id: str

    # raw data
    input_text: str
    ground_truth: GroundTruth
    raw_prediction: str
    parsed_prediction: dict[str, Any] | None
    parse_error: str | None
    latency_ms: float

    # scores
    classification: ClassificationScores | None = None
    llm_judge: LLMJudgeScores | None = None
    semantic: SemanticScores | None = None

    # top-level eval status
    eval_errors: list[str] = Field(default_factory=list)


# ================================================================ Aggregate report


class AggregateMetrics(BaseModel):
    """Mean/distribution metrics across all samples in a run."""

    n_samples: int
    n_parse_errors: int
    n_schema_errors: int
    n_foundational: int = Field(
        default=0,
        description="Samples with no selected_predecessor_id — excluded from predecessor metrics.",
    )

    # classification (computed over non-foundational samples only)
    predecessor_accuracy: float
    predecessor_soft_accuracy: float = Field(
        default=0.0,
        description="Soft accuracy: exact match OR pred appears in GT secondary_influences.",
    )
    predecessor_mrr: float
    breakthrough_level_accuracy: float
    secondary_influences_f1_mean: float

    # llm judge (means across judged samples — comparison fields exclude foundation papers)
    judge_selection_reasoning_mean: float
    judge_what_was_improved_mean: float
    judge_how_it_was_improved_mean: float
    judge_why_it_matters_mean: float
    judge_problem_solved_mean: float
    judge_overall_mean: float

    # semantic similarity
    semantic_eli5_mean: float
    semantic_intuitive_mean: float
    semantic_technical_mean: float
    semantic_overall_mean: float


class EvalReport(BaseModel):
    """Top-level report written to GCS after a run."""

    run_id: str
    config_snapshot: dict[str, Any]
    aggregate: AggregateMetrics
    per_sample_gcs_path: str = Field(
        description="GCS URI of the JSONL file containing per-sample results."
    )