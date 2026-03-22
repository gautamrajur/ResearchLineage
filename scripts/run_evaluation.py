# scripts/run_evaluation.py
"""
End-to-end evaluation pipeline runner.
Runs all four stages: load → infer → evaluate → save.

Usage:
    poetry run python scripts/run_evaluation.py
    poetry run python scripts/run_evaluation.py --input gs://research-lineage-eval/eval/inputs/val_data.jsonl
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv

load_dotenv()


# ------------------------------------------------------------------ logging setup

_LOG_RECORD_BUILTINS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)

class CleanFormatter(logging.Formatter):
    """
    Compact formatter: timestamp [LEVEL] logger_name — message | key=value ...
    Only appends extra fields that were explicitly passed by the caller.
    """
    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        extras = {
            k: v for k, v in record.__dict__.items()
            if k not in _LOG_RECORD_BUILTINS
            and k not in ("message", "asctime")
        }
        if extras:
            kv = "  ".join(f"{k}={v}" for k, v in extras.items())
            msg = f"{msg}  |  {kv}"
        return msg


def _setup_logging() -> Path:
    """
    Set up console (INFO) and file (DEBUG) handlers.
    Returns the log file path.
    """
    run_ts = time.strftime("%Y%m%d_%H%M%S")
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / f"run_{run_ts}.log"

    fmt = CleanFormatter(
        fmt="%(asctime)s [%(levelname)-8s] %(name)-40s — %(message)s",
        datefmt="%H:%M:%S",
    )

    # console handler — INFO only, clean output
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)

    # file handler — DEBUG level, real-time flush, captures everything
    file_handler = logging.FileHandler(log_path, mode="w", encoding="utf-8", delay=False)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers = [console, file_handler]

    # silence noisy third-party loggers globally (console + file)
    for noisy in ("httpx", "httpcore", "sentence_transformers", "urllib3", "google", "pydot"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    return log_path

logger = logging.getLogger("run_evaluation")


# ------------------------------------------------------------------ main

def main() -> None:
    log_path = _setup_logging()
    logger = logging.getLogger("run_evaluation")

    parser = argparse.ArgumentParser(description="Run the LLM evaluation pipeline.")
    parser.add_argument(
        "--input",
        default=None,
        help="Override GCS input path (default: EVAL_GCS_INPUT_PATH from .env). "
             "Ignored when --ft-format is set.",
    )
    parser.add_argument(
        "--ft-format",
        default=None,
        metavar="LOCAL_JSONL_PATH",
        help="Load samples from a local fine-tuning JSONL file (chat format) instead "
             "of GCS. Extracts input_text from the user section and ground_truth from "
             "the assistant section on the fly. "
             "e.g. --ft-format temporary/ft_data/test_converted.jsonl",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load and validate data only — skip inference and evaluation.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only evaluate the first N samples. Useful for smoke testing.",
    )
    args = parser.parse_args()

    # ---------------------------------------------------------------- config
    from src.evaluation.config import EvaluationConfig

    cfg = EvaluationConfig()
    if args.input:
        cfg.gcs_input_path = args.input

    ft_format_path = args.ft_format  # local path to FT-format JSONL, or None

    if cfg.openai_base_url and cfg.openai_model:
        model_label = f"{cfg.openai_model} @ {cfg.openai_base_url}"
    elif cfg.modal_endpoint_url:
        model_label = cfg.modal_endpoint_url
    else:
        model_label = cfg.vertex_endpoint_id

    logger.info("=" * 60)
    logger.info("EVALUATION PIPELINE STARTING")
    logger.info("=" * 60)
    logger.info(f"Log file : {log_path.resolve()}")
    logger.info(f"Input  : {cfg.gcs_input_path}")
    logger.info(f"Output : {cfg.gcs_output_path}")
    logger.info(f"Model  : {model_label} ({cfg.inference_model_name})")
    logger.info(f"Judge  : {cfg.judge_model_name}")

    # ---------------------------------------------------------------- stage 1: load
    from src.evaluation.pipeline import load_eval_data, load_ft_format_as_eval_data

    logger.info("\n[STAGE 1/4] Loading evaluation data...")
    t0 = time.monotonic()
    if ft_format_path:
        logger.info(f"Source : FT chat format — {ft_format_path}")
        samples = load_ft_format_as_eval_data(ft_format_path)
    else:
        logger.info(f"Source : GCS — {cfg.gcs_input_path}")
        samples = load_eval_data(cfg)
    logger.info(f"Loaded {len(samples)} samples in {time.monotonic()-t0:.1f}s")

    if args.dry_run:
        logger.info("Dry run complete — skipping inference and evaluation.")
        sys.exit(0)

    if args.limit:
        samples = samples[:args.limit]
        logger.info(f"Limited to first {args.limit} samples")

    if not samples:
        logger.error("No samples loaded. Aborting.")
        sys.exit(1)

    # ---------------------------------------------------------------- stage 2: infer
    from src.evaluation.pipeline import run_inference

    logger.info(f"\n[STAGE 2/4] Running inference on {len(samples)} samples...")
    t0 = time.monotonic()
    inference_results = run_inference(samples, cfg)
    n_errors = sum(1 for r in inference_results if r.parse_error)
    logger.info(
        f"Inference complete in {time.monotonic()-t0:.1f}s "
        f"({len(inference_results) - n_errors} ok, {n_errors} errors)"
    )

    # ---------------------------------------------------------------- stage 3: evaluate
    from src.evaluation.pipeline import evaluate_all

    logger.info(f"\n[STAGE 3/4] Running evaluators on {len(inference_results)} results...")
    t0 = time.monotonic()
    eval_results = evaluate_all(samples, inference_results, cfg)
    logger.info(f"Evaluation complete in {time.monotonic()-t0:.1f}s")

    # ---------------------------------------------------------------- stage 4: save
    from src.evaluation.pipeline import save_results

    logger.info(f"\n[STAGE 4/4] Saving results to GCS...")
    t0 = time.monotonic()
    report = save_results(eval_results, cfg)
    logger.info(f"Saved in {time.monotonic()-t0:.1f}s")

    # ---------------------------------------------------------------- summary
    agg = report.aggregate
    logger.info("\n" + "=" * 60)
    logger.info("EVALUATION SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Run ID              : {report.run_id}")
    logger.info(f"Samples evaluated   : {agg.n_samples}")
    logger.info(f"Parse errors        : {agg.n_parse_errors}")
    logger.info(f"Schema errors       : {agg.n_schema_errors}")
    logger.info("")
    logger.info(f"Predecessor accuracy: {agg.predecessor_accuracy:.3f}")
    logger.info(f"Predecessor MRR     : {agg.predecessor_mrr:.3f}")
    logger.info(f"Breakthrough acc    : {agg.breakthrough_level_accuracy:.3f}")
    logger.info(f"Influences F1       : {agg.secondary_influences_f1_mean:.3f}")
    logger.info("")
    logger.info(f"Judge overall mean  : {agg.judge_overall_mean:.3f} / 5.0")
    logger.info(f"  selection_reasoning : {agg.judge_selection_reasoning_mean:.3f}")
    logger.info(f"  what_was_improved   : {agg.judge_what_was_improved_mean:.3f}")
    logger.info(f"  how_it_was_improved : {agg.judge_how_it_was_improved_mean:.3f}")
    logger.info(f"  why_it_matters      : {agg.judge_why_it_matters_mean:.3f}")
    logger.info(f"  problem_solved      : {agg.judge_problem_solved_mean:.3f}")
    logger.info("")
    logger.info(f"Semantic overall    : {agg.semantic_overall_mean:.3f}")
    logger.info(f"  eli5               : {agg.semantic_eli5_mean:.3f}")
    logger.info(f"  intuitive          : {agg.semantic_intuitive_mean:.3f}")
    logger.info(f"  technical          : {agg.semantic_technical_mean:.3f}")
    logger.info("")
    logger.info(f"Results saved to    : {report.per_sample_gcs_path}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()