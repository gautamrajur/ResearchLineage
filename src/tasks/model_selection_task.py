"""
model_selection_task.py
=======================
CLI wrapper for multi-model comparison, selection, and visualization.

Usage:
  python model_selection_task.py \
    --report-dirs /tmp/eval_qwen7b /tmp/eval_qwen72b /tmp/eval_gemini \
    --model-names qwen-7b-finetuned qwen-72b-base gemini-2.5-pro \
    --output-dir /tmp/model_comparison \
    --generate-viz \
    --promote
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.model_selection import load_reports_from_dirs, select_best_model
from src.utils.config import GCS_BUCKET_NAME, GCS_PROJECT_ID
from src.utils.logging import get_logger

logger = get_logger(__name__)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Multi-model comparison and selection")

    p.add_argument(
        "--report-dirs", nargs="+", required=True,
        help="Directories containing aggregate_report.json for each model",
    )
    p.add_argument(
        "--model-names", nargs="+", required=True,
        help="Names for each model (must match --report-dirs count)",
    )
    p.add_argument("--output-dir", default="/tmp/model_comparison")
    p.add_argument("--generate-viz", action="store_true", help="Generate comparison charts + HTML report")
    p.add_argument("--promote", action="store_true", help="Promote winner to production if it beats current model")

    # GCS upload (for comparison artifacts)
    p.add_argument("--bucket", default=GCS_BUCKET_NAME)
    p.add_argument("--project", default=GCS_PROJECT_ID)
    p.add_argument("--upload", action="store_true", help="Upload comparison artifacts to GCS")

    return p.parse_args()


def run_selection(args: argparse.Namespace) -> dict:
    """Load reports, run selection, write results."""
    if len(args.report_dirs) != len(args.model_names):
        logger.error("--report-dirs count (%d) != --model-names count (%d)", len(args.report_dirs), len(args.model_names))
        sys.exit(1)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load reports
    logger.info("model_selection loading reports from %d directories", len(args.report_dirs))
    reports = load_reports_from_dirs(args.report_dirs, args.model_names)

    # Run selection
    result = select_best_model(reports)

    # Write selection report
    report_path = output_dir / "model_selection_report.json"
    # Strip full reports from saved JSON (too large), keep scores + rankings
    save_result = {k: v for k, v in result.items() if k != "reports"}
    report_path.write_text(json.dumps(save_result, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("model_selection winner=%s composite=%.4f report=%s",
                result["winner"], result["scores"][result["winner"]]["composite"], report_path)

    # Rankings
    for rank, (name, score) in enumerate(result["rankings"], 1):
        logger.info("  model_selection rank=%d name=%s composite=%.4f", rank, name, score)

    return result


def run_visualization(result: dict, output_dir: str) -> list[str]:
    """Generate comparison charts + HTML report."""
    from src.evaluation.visualization import generate_comparison_report

    logger.info("model_selection generating visualizations")
    paths = generate_comparison_report(result, output_dir)
    logger.info("model_selection generated %d visualization files: %s", len(paths), paths)
    return paths


def log_to_mlflow(result: dict, artifact_dir: str | None = None) -> None:
    """Log comparison results to MLflow."""
    try:
        from src.mlflow_utils import log_model_comparison

        run_id = log_model_comparison(result, artifact_dir=artifact_dir)
        logger.info("model_selection MLflow run_id=%s", run_id)
    except Exception as exc:
        logger.warning("model_selection MLflow logging skipped: %s", exc)


def run_promotion(result: dict, project_id: str, bucket_name: str) -> bool:
    """Promote winner if it beats the current production model.

    Returns True if promotion happened.
    """
    from src.registry.artifact_registry import list_model_versions, promote_model

    winner = result["winner"]
    winner_score = result["scores"][winner]["composite"]

    # Check current production model
    versions = list_model_versions(bucket_name=bucket_name, project_id=project_id)
    current_prod = None
    for v in versions:
        if v.get("stage") == "production":
            current_prod = v
            break

    if current_prod:
        current_score = current_prod.get("composite_score", 0.0)
        logger.info("promote current_prod=%s composite=%.4f challenger=%s composite=%.4f",
                    current_prod["version"], current_score, winner, winner_score)

        if winner_score <= current_score:
            logger.info("promote: current model retained — winner does not beat production")
            return False

    logger.info("promote: promoting %s to production", winner)

    # Find winner's version in registry, or register if not found
    winner_version = None
    for v in versions:
        if winner.lower() in v.get("version", "").lower():
            winner_version = v["version"]
            break

    if winner_version:
        promote_model(
            version=winner_version,
            stage="production",
            bucket_name=bucket_name,
            project_id=project_id,
        )
        logger.info("promote: PROMOTED %s to production", winner_version)
        return True
    else:
        logger.warning("promote: no registry entry found for winner=%r — skipping promotion", winner)
        return False


def upload_to_gcs(output_dir: str, bucket_name: str, project_id: str) -> None:
    """Upload comparison artifacts to GCS."""
    from google.cloud import storage

    client = storage.Client(project=project_id)
    bucket = client.bucket(bucket_name)
    gcs_prefix = "fine-tuning-artifacts/model_comparison"

    output_path = Path(output_dir)
    for file_path in output_path.iterdir():
        if file_path.is_file():
            blob_name = f"{gcs_prefix}/{file_path.name}"
            bucket.blob(blob_name).upload_from_filename(str(file_path))
            logger.info("upload %s → gs://%s/%s", file_path.name, bucket_name, blob_name)

    logger.info("upload done gcs_prefix=gs://%s/%s", bucket_name, gcs_prefix)


if __name__ == "__main__":
    args = _parse_args()

    # 1. Run selection
    result = run_selection(args)

    # 2. Generate visualizations
    viz_paths = []
    if args.generate_viz:
        viz_paths = run_visualization(result, args.output_dir)

    # 3. Log to MLflow
    log_to_mlflow(result, artifact_dir=args.output_dir if args.generate_viz else None)

    # 4. Promote winner
    promoted = False
    if args.promote:
        promoted = run_promotion(result, project_id=args.project, bucket_name=args.bucket)

    # 5. Upload to GCS
    if args.upload:
        upload_to_gcs(args.output_dir, args.bucket, args.project)

    # Output for CI/CD consumption
    print(f"\nPROMOTE={'true' if promoted else 'false'}")
    print(f"WINNER={result['winner']}")
