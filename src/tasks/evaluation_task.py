"""
evaluation_task.py
==================
Self-contained task script for the evaluate_performance DAG.

Steps (controlled by --step flag):
  run_inference   — generate model predictions on the test split
  evaluate        — compute classification metrics (non-foundational) +
                    LLM-as-judge metrics (all samples including foundational)
  upload          — push per_sample JSONL + aggregate JSON/TXT to GCS

Input can be a local path OR a GCS URI:
  --local-input   path to test.jsonl  (local)
  --gcs-input     gs://bucket/path/to/test.jsonl  (GCS)

Usage (Airflow BashOperator calls these):
  python evaluation_task.py --step run_inference  --local-input /path/test.jsonl  --output-dir /tmp/eval
  python evaluation_task.py --step evaluate       --output-dir /tmp/eval --vertex-project my-proj --judge-model gemini-2.5-flash
  python evaluation_task.py --step upload         --output-dir /tmp/eval --bucket my-bucket --project my-proj
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

# Make src importable from project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.config import EvaluationConfig
from src.evaluation.evaluators.classification import evaluate_classification
from src.evaluation.evaluators.llm_judge import evaluate_llm_judge
from src.evaluation.gcs_utils import (
    load_jsonl_from_gcs,
    save_json_to_gcs,
    save_jsonl_to_gcs,
)
from src.evaluation.model_client import build_inference_client, build_judge_client
from src.evaluation.pipeline import _flatten_ground_truth, _parse_model_output
from src.evaluation.types import GroundTruth
from src.utils.config import GCS_BUCKET_NAME, GCS_PROJECT_ID

# ── Constants ─────────────────────────────────────────────────────────────────

MAX_INPUT_CHARS = 350_000
MAX_RETRIES = 6
RETRY_DELAYS = [30, 60, 120, 120, 120, 120]

CITATION_TIERS = [
    ("low",    0,       5_100),
    ("medium", 5_100,   12_327),
    ("high",   12_327,  31_913),
    ("viral",  31_913,  float("inf")),
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean_json(s: str) -> dict:
    return json.loads(re.sub(r",\s*([}\]])", r"\1", s))


def _citation_tier(n: int | None) -> str:
    if n is None:
        return "unknown"
    for name, lo, hi in CITATION_TIERS:
        if lo <= n < hi:
            return name
    return "viral"


def _mean(vals: list) -> float | None:
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 4) if vals else None


def _load_jsonl_local(path: str) -> list[dict]:
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _load_input(local_path: str | None, gcs_uri: str | None, project_id: str) -> list[dict]:
    """Load JSONL from local path or GCS URI."""
    if local_path:
        return _load_jsonl_local(local_path)
    if gcs_uri:
        return load_jsonl_from_gcs(gcs_uri=gcs_uri, project_id=project_id)
    raise ValueError("Must provide --local-input or --gcs-input")


def _load_metadata(local_input: str | None, gcs_input: str | None, project_id: str) -> dict[str, dict]:
    """
    Derive metadata path from input path.
    e.g. .../test.jsonl → .../test_metadata_fixed.jsonl
    Works for both local and GCS paths.
    """
    base = local_input or gcs_input
    meta_path = re.sub(r"([^/\\]+)\.jsonl$", lambda m: f"{m.group(1)}_metadata_fixed.jsonl", base)
    try:
        records = _load_input(
            local_path=meta_path if local_input else None,
            gcs_uri=meta_path if gcs_input else None,
            project_id=project_id,
        )
        return {f"sample_{r['sample_index']:05d}": r for r in records}
    except Exception:
        return {}


# ══════════════════════════════════════════════════════════════════
# STEP 1: run_inference
# ══════════════════════════════════════════════════════════════════

def run_inference(args: argparse.Namespace) -> None:
    """
    Generate model predictions on the test split.
    Writes per_sample_raw.jsonl to output_dir.
    Resumable: skips sample_ids already successfully saved.
    """
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "per_sample_raw.jsonl"

    cfg = EvaluationConfig(
        finetuning_data_source=args.data_source,
        finetuning_data_gcs_path=args.gcs_input or "",
        gcs_output_path=f"gs://{args.bucket}/{args.gcs_output_prefix}",
        gcs_project_id=args.project,
        vertex_project_id=args.vertex_project,
        vertex_location=args.vertex_location,
        model_endpoint=args.model_endpoint,
        max_workers=args.max_workers,
    )

    # Load input samples
    local_input = args.local_input if args.data_source == "local" else None
    gcs_input = args.gcs_input if args.data_source != "local" else None
    records = _load_input(local_input, gcs_input, args.project)
    meta_map = _load_metadata(local_input, gcs_input, args.project)

    # Build EvalSample-like dicts (lightweight, no Pydantic needed here)
    samples = []
    for i, record in enumerate(records):
        sid = f"sample_{i:05d}"
        gt_raw = record.get("output_text") or record.get("ground_truth", {})
        if isinstance(gt_raw, str):
            gt_raw = _clean_json(gt_raw)
        samples.append({
            "sample_id": sid,
            "input_text": record["input_text"],
            "ground_truth": gt_raw,
            "meta": meta_map.get(sid, {}),
        })

    # Load already-completed results
    done: dict[str, dict] = {}
    if raw_path.exists():
        for line in raw_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if not r.get("error") and not r.get("parse_error"):
                    done[r["sample_id"]] = r

    todo = [s for s in samples if s["sample_id"] not in done]
    print(f"[run_inference] total={len(samples)}  done={len(done)}  to_run={len(todo)}")

    if not todo:
        print("[run_inference] All samples already complete.")
        return

    client = build_inference_client(
        model_endpoint=cfg.model_endpoint,
        project_id=cfg.vertex_project_id or cfg.gcs_project_id,
        location=cfg.vertex_location,
    )
    run_id = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")

    def _infer_one(sample: dict) -> dict:
        last_exc = None
        for attempt in range(MAX_RETRIES + 1):
            start = time.monotonic()
            try:
                raw = client.predict(sample["input_text"][:MAX_INPUT_CHARS])
                latency_ms = (time.monotonic() - start) * 1000
                parsed, parse_error = _parse_model_output(raw)
                print(f"  OK  {sample['sample_id']}  attempt={attempt+1}  latency={latency_ms:.0f}ms")
                return {
                    "sample_id":        sample["sample_id"],
                    "run_id":           run_id,
                    "raw_prediction":   raw,
                    "parsed_prediction": parsed,
                    "parse_error":      parse_error,
                    "latency_ms":       latency_ms,
                    "error":            None,
                    "attempts":         attempt + 1,
                    "ground_truth":     sample["ground_truth"],
                    "meta":             sample["meta"],
                }
            except Exception as exc:
                latency_ms = (time.monotonic() - start) * 1000
                last_exc = exc
                is_last = attempt == MAX_RETRIES
                print(
                    f"  {'FAIL' if is_last else 'RETRY'}  {sample['sample_id']}  "
                    f"attempt={attempt+1}  {type(exc).__name__}: {str(exc)[:120]}"
                )
                if not is_last:
                    time.sleep(RETRY_DELAYS[attempt])

        return {
            "sample_id":        sample["sample_id"],
            "run_id":           run_id,
            "raw_prediction":   "",
            "parsed_prediction": None,
            "parse_error":      str(last_exc),
            "latency_ms":       0.0,
            "error":            type(last_exc).__name__,
            "attempts":         MAX_RETRIES + 1,
            "ground_truth":     sample["ground_truth"],
            "meta":             sample["meta"],
        }

    completed = ok = errors = 0
    with open(raw_path, "a", encoding="utf-8") as f:
        with ThreadPoolExecutor(max_workers=cfg.max_workers) as executor:
            futures = {executor.submit(_infer_one, s): s["sample_id"] for s in todo}
            for future in as_completed(futures):
                result = future.result()
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
                f.flush()
                completed += 1
                if not result["error"] and not result["parse_error"]:
                    ok += 1
                else:
                    errors += 1
                print(f"  Progress {completed}/{len(todo)}  ok={ok}  errors={errors}")

    print(f"[run_inference] Done. ok={ok}  errors={errors}  saved to {raw_path}")


# ══════════════════════════════════════════════════════════════════
# STEP 2: evaluate
# ══════════════════════════════════════════════════════════════════

def evaluate(args: argparse.Namespace) -> None:
    """
    Compute evaluation metrics:
      - Classification (predecessor accuracy, MRR, breakthrough, F1) — non-foundational only
      - LLM-as-judge (5 reasoning fields, 1-5 scale) — ALL samples including foundational

    Reads per_sample_raw.jsonl, writes:
      - per_sample_results.jsonl
      - aggregate_report.json
      - aggregate_report.txt
    """
    output_dir = Path(args.output_dir)
    raw_path = output_dir / "per_sample_raw.jsonl"

    if not raw_path.exists():
        raise FileNotFoundError(f"Run inference first — {raw_path} not found.")

    raw_records = _load_jsonl_local(str(raw_path))
    print(f"[evaluate] Loaded {len(raw_records)} inference results")

    # Build judge client once — used for ALL samples including foundational
    judge_client = build_judge_client(
        project_id=args.vertex_project,
        location=args.vertex_location,
        model_name=args.judge_model,
        max_output_tokens=args.judge_max_tokens,
    )
    judge_model_id = args.judge_model

    rows = []
    n_foundational = 0
    n_errors = 0

    for idx, r in enumerate(raw_records):
        pro_pred = r.get("parsed_prediction") or {}   # model output
        flash_pred = r.get("ground_truth") or {}       # GT from test.jsonl

        # Foundational = GT has no predecessor
        is_foundational = not flash_pred.get("selected_predecessor_id")
        has_error = bool(r.get("error") or r.get("parse_error"))

        meta = r.get("meta", {})

        # ── LLM Judge (ALL samples, including foundational) ───────────────────
        judge_scores_dict: dict = {}
        try:
            gt_flat = _flatten_ground_truth(flash_pred)
            ground_truth_judge = GroundTruth(**gt_flat)
            judge_scores = evaluate_llm_judge(
                prediction=pro_pred if not has_error else None,
                ground_truth=ground_truth_judge,
                judge_client=judge_client,
                judge_model_id=judge_model_id,
                sample_id=r["sample_id"],
                sample_index=idx,
                total_samples=len(raw_records),
            )
            judge_scores_dict = {
                "judge_selection_reasoning": judge_scores.selection_reasoning.score,
                "judge_what_was_improved":   judge_scores.what_was_improved.score,
                "judge_how_it_was_improved": judge_scores.how_it_was_improved.score,
                "judge_why_it_matters":      judge_scores.why_it_matters.score,
                "judge_problem_solved":      judge_scores.problem_solved_from_predecessor.score,
                "judge_overall": round(sum([
                    judge_scores.selection_reasoning.score,
                    judge_scores.what_was_improved.score,
                    judge_scores.how_it_was_improved.score,
                    judge_scores.why_it_matters.score,
                    judge_scores.problem_solved_from_predecessor.score,
                ]) / 5, 4),
            }
        except Exception as e:
            print(f"  WARNING: Judge failed for {r['sample_id']}: {e}")
            judge_scores_dict = {
                "judge_selection_reasoning": -1.0,
                "judge_what_was_improved":   -1.0,
                "judge_how_it_was_improved": -1.0,
                "judge_why_it_matters":      -1.0,
                "judge_problem_solved":      -1.0,
                "judge_overall":             -1.0,
            }

        # ── Classification (non-foundational without errors only) ─────────────
        cls_scores_dict: dict = {
            "predecessor_strict": None,
            "predecessor_soft":   None,
            "mrr":                None,
            "breakthrough":       None,
            "secondary_f1":       None,
            "schema_valid":       None,
        }
        if is_foundational:
            n_foundational += 1
        elif has_error:
            n_errors += 1
        else:
            try:
                # pro_pred (model output) used as ground truth reference for classification
                gt_flat_cls = _flatten_ground_truth(pro_pred)
                ground_truth_cls = GroundTruth(**gt_flat_cls)
                scores = evaluate_classification(prediction=flash_pred, ground_truth=ground_truth_cls)

                pro_secondary_ids = {
                    x.get("paper_id") for x in pro_pred.get("secondary_influences", [])
                    if isinstance(x, dict)
                }
                flash_pick = flash_pred.get("selected_predecessor_id")
                soft_correct = scores.predecessor_id_correct or (flash_pick in pro_secondary_ids)

                cls_scores_dict = {
                    "predecessor_strict": scores.predecessor_id_correct,
                    "predecessor_soft":   soft_correct,
                    "mrr":                scores.predecessor_id_mrr,
                    "breakthrough":       scores.breakthrough_level_correct,
                    "secondary_f1":       scores.secondary_influences_f1,
                    "schema_valid":       scores.schema_valid,
                }
            except Exception as e:
                print(f"  WARNING: Classification failed for {r['sample_id']}: {e}")
                n_errors += 1

        row = {
            "sample_id":       r["sample_id"],
            "run_id":          r.get("run_id", ""),
            "is_foundational": is_foundational,
            "domain":          meta.get("domain_classification", {}).get("gemini_field", "unknown"),
            "citation_count":  meta.get("seed_citation_count"),
            "citation_tier":   _citation_tier(meta.get("seed_citation_count")),
            "latency_ms":      r.get("latency_ms", 0),
            **cls_scores_dict,
            **judge_scores_dict,
        }
        rows.append(row)

        print(
            f"  [{idx+1}/{len(raw_records)}] {r['sample_id']}"
            f"  foundational={is_foundational}"
            f"  judge_overall={judge_scores_dict.get('judge_overall')}"
        )

    n_cls_evaluated = sum(1 for r in rows if r.get("predecessor_strict") is not None)
    n_judge_evaluated = sum(1 for r in rows if r.get("judge_overall") is not None)
    print(
        f"[evaluate] n_total={len(raw_records)}"
        f"  n_foundational={n_foundational}"
        f"  n_errors={n_errors}"
        f"  n_cls={n_cls_evaluated}"
        f"  n_judge={n_judge_evaluated}"
    )

    # ── Per-sample JSONL ──────────────────────────────────────────────────────
    per_sample_path = output_dir / "per_sample_results.jsonl"
    with open(per_sample_path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # ── Aggregate ─────────────────────────────────────────────────────────────
    cls_rows   = [r for r in rows if r.get("predecessor_strict") is not None]
    judge_rows = [r for r in rows if r.get("judge_overall") is not None]

    def agg_cls(subset: list[dict]) -> dict | None:
        if not subset:
            return None
        n = len(subset)
        return {
            "n": n,
            "predecessor_strict": _mean([r["predecessor_strict"] for r in subset]),
            "predecessor_soft":   _mean([r["predecessor_soft"]   for r in subset]),
            "mrr":                _mean([r["mrr"]                for r in subset]),
            "breakthrough":       _mean([r["breakthrough"]       for r in subset]),
            "secondary_f1":       _mean([r["secondary_f1"]       for r in subset]),
            "schema_valid":       _mean([r["schema_valid"]        for r in subset]),
        }

    def agg_judge(subset: list[dict]) -> dict | None:
        if not subset:
            return None
        # Exclude -1 sentinel (failed calls) from means
        def _jmean(key: str) -> float | None:
            vals = [r[key] for r in subset if r.get(key) is not None and r[key] >= 0]
            return _mean(vals)
        n = len(subset)
        n_failed = sum(1 for r in subset if r.get("judge_overall", -1) < 0)
        return {
            "n": n,
            "n_failed": n_failed,
            "judge_selection_reasoning": _jmean("judge_selection_reasoning"),
            "judge_what_was_improved":   _jmean("judge_what_was_improved"),
            "judge_how_it_was_improved": _jmean("judge_how_it_was_improved"),
            "judge_why_it_matters":      _jmean("judge_why_it_matters"),
            "judge_problem_solved":      _jmean("judge_problem_solved"),
            "judge_overall":             _jmean("judge_overall"),
        }

    all_domains = sorted({r["domain"] for r in rows})
    all_tiers = [t for t in ["low", "medium", "high", "viral", "unknown"]
                 if any(r["citation_tier"] == t for r in rows)]

    report: dict = {
        "generated_at":              datetime.now(tz=timezone.utc).isoformat(),
        "n_total":                   len(raw_records),
        "n_evaluated":               len(rows),
        "n_foundational":            n_foundational,
        "n_errors":                  n_errors,
        "n_classification_evaluated": n_cls_evaluated,
        "n_judge_evaluated":          n_judge_evaluated,
        "overall_classification":    agg_cls(cls_rows),
        "overall_judge":             agg_judge(judge_rows),
        "by_domain": {
            dom: {
                "classification": agg_cls([r for r in cls_rows   if r["domain"] == dom]),
                "judge":          agg_judge([r for r in judge_rows if r["domain"] == dom]),
            }
            for dom in all_domains
        },
        "by_citation_tier": {
            tier: {
                "classification": agg_cls([r for r in cls_rows   if r["citation_tier"] == tier]),
                "judge":          agg_judge([r for r in judge_rows if r["citation_tier"] == tier]),
            }
            for tier in all_tiers
        },
    }

    # ── JSON ──
    json_path = output_dir / "aggregate_report.json"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    # ── TXT ──
    txt_path = output_dir / "aggregate_report.txt"
    txt_path.write_text(_build_txt(report), encoding="utf-8")

    print(f"[evaluate] Reports written to {output_dir}")


# ── Report formatters ─────────────────────────────────────────────────────────

def _fmt_cls(m: dict | None, indent: str = "  ") -> str:
    if not m:
        return f"{indent}(no data)"
    lines = [
        f"{indent}n                      {m['n']}",
        f"{indent}Predecessor strict     {m['predecessor_strict']:.4f}",
        f"{indent}Predecessor soft       {m['predecessor_soft']:.4f}",
        f"{indent}MRR                    {m['mrr']:.4f}",
        f"{indent}Breakthrough accuracy  {m['breakthrough']:.4f}",
        f"{indent}Secondary F1           {m['secondary_f1']:.4f}",
        f"{indent}Schema valid rate      {m['schema_valid']:.4f}",
    ]
    return "\n".join(lines)


def _fmt_judge(m: dict | None, indent: str = "  ") -> str:
    if not m:
        return f"{indent}(no data)"

    def _f(v):
        return f"{v:.4f}" if v is not None else "n/a (all failed)"

    lines = [
        f"{indent}n                        {m['n']}  (failed={m.get('n_failed', 0)})",
        f"{indent}Selection reasoning      {_f(m['judge_selection_reasoning'])}",
        f"{indent}What was improved        {_f(m['judge_what_was_improved'])}",
        f"{indent}How it was improved      {_f(m['judge_how_it_was_improved'])}",
        f"{indent}Why it matters           {_f(m['judge_why_it_matters'])}",
        f"{indent}Problem solved           {_f(m['judge_problem_solved'])}",
        f"{indent}Overall                  {_f(m['judge_overall'])}",
    ]
    return "\n".join(lines)


def _build_txt(report: dict) -> str:
    SEP = "=" * 60
    SEP2 = "-" * 60
    lines = [
        SEP,
        "  EVALUATION REPORT",
        f"  Generated: {report['generated_at']}",
        SEP,
        "",
        f"  Total inference samples        : {report['n_total']}",
        f"  Total evaluated                : {report['n_evaluated']}",
        f"  Foundational (no predecessor)  : {report['n_foundational']}",
        f"  Errors                         : {report['n_errors']}",
        f"  Classification evaluated       : {report['n_classification_evaluated']}",
        f"  Judge evaluated                : {report['n_judge_evaluated']}",
        "",
        "OVERALL — CLASSIFICATION  (non-foundational only)",
        SEP2,
        _fmt_cls(report["overall_classification"]),
        "",
        "OVERALL — LLM JUDGE  (all samples including foundational)",
        SEP2,
        _fmt_judge(report["overall_judge"]),
        "",
        "BY DOMAIN",
        SEP2,
    ]
    for dom, m in report["by_domain"].items():
        lines += [
            f"  [{dom}]",
            "    Classification:",
            _fmt_cls(m.get("classification"), indent="      "),
            "    LLM Judge:",
            _fmt_judge(m.get("judge"), indent="      "),
            "",
        ]
    lines += ["BY CITATION TIER", SEP2]
    for tier, m in report["by_citation_tier"].items():
        lines += [
            f"  [{tier}]",
            "    Classification:",
            _fmt_cls(m.get("classification"), indent="      "),
            "    LLM Judge:",
            _fmt_judge(m.get("judge"), indent="      "),
            "",
        ]
    lines.append(SEP)
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
# STEP 3: upload
# ══════════════════════════════════════════════════════════════════

def upload(args: argparse.Namespace) -> None:
    """Push evaluation outputs to GCS.

    Output path is derived from the input GCS path:
      <parent of input JSONL>/evaluation_artifacts/
    e.g. gs://bucket/path/test.jsonl → gs://bucket/path/evaluation_artifacts/
    """
    output_dir = Path(args.output_dir)

    # Derive GCS output prefix from input path parent
    gcs_input = args.gcs_input.rstrip("/")
    if gcs_input and gcs_input.startswith("gs://"):
        # Strip the filename to get the parent directory
        parent = gcs_input.rsplit("/", 1)[0]  # e.g. gs://bucket/path/dir
        base_gcs = f"{parent}/evaluation_artifacts"
    else:
        # Fallback to old behaviour if no GCS input provided
        agg_path = output_dir / "aggregate_report.json"
        run_id = "unknown"
        if agg_path.exists():
            data = json.loads(agg_path.read_text(encoding="utf-8"))
            run_id = data.get("generated_at", "unknown").replace(":", "").replace("-", "")[:15]
        base_gcs = f"gs://{args.bucket}/{args.gcs_output_prefix}/evaluation_metrics/{run_id}"

    files = {
        "per_sample_results.jsonl": f"{base_gcs}/per_sample_results.jsonl",
        "aggregate_report.json":    f"{base_gcs}/aggregate_report.json",
        "aggregate_report.txt":     f"{base_gcs}/aggregate_report.txt",
    }

    for filename, gcs_uri in files.items():
        local_file = output_dir / filename
        if not local_file.exists():
            print(f"  SKIP (not found): {filename}")
            continue

        if filename.endswith(".jsonl"):
            records = [json.loads(l) for l in local_file.read_text(encoding="utf-8").splitlines() if l.strip()]
            save_jsonl_to_gcs(records=records, gcs_uri=gcs_uri, project_id=args.project)
        else:
            content = local_file.read_text(encoding="utf-8")
            from google.cloud import storage
            bucket_name, blob_name = gcs_uri[5:].split("/", 1)
            client = storage.Client(project=args.project)
            client.bucket(bucket_name).blob(blob_name).upload_from_string(
                content,
                content_type="application/json" if filename.endswith(".json") else "text/plain",
            )
        print(f"  Uploaded: {filename} → {gcs_uri}")

    print(f"[upload] Done. GCS prefix: {base_gcs}")


# ══════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluation task runner")
    p.add_argument("--step", required=True, choices=["run_inference", "evaluate", "upload", "bias_check"])

    # Input
    p.add_argument("--data-source",  default="local", choices=["local", "gcs"],
                   help="Where to load input data from")
    p.add_argument("--local-input",  default="", help="Local path to test.jsonl (used when --data-source=local)")
    p.add_argument("--gcs-input",    default="", help="GCS URI to test.jsonl (used when --data-source=gcs)")

    # Output
    p.add_argument("--output-dir",   default="/tmp/eval_output", help="Local working directory for outputs")

    # GCS upload
    p.add_argument("--bucket",            default=GCS_BUCKET_NAME)
    p.add_argument("--project",           default=GCS_PROJECT_ID)
    p.add_argument("--gcs-output-prefix", default="fine-tuning-artifacts", dest="gcs_output_prefix")

    # Inference
    p.add_argument("--model-endpoint",   default="gemini-2.5-pro",
                   help="gemini-* → GeminiClient, http* → ModalClient, else → VertexAI endpoint ID")
    p.add_argument("--vertex-project",   default="testing-488212")
    p.add_argument("--vertex-location",  default="us-central1")
    p.add_argument("--max-workers",      type=int, default=2)

    # Judge (used in evaluate step)
    p.add_argument("--judge-model",      default="gemini-2.5-flash",
                   help="Gemini model name for LLM-as-judge evaluation")
    p.add_argument("--judge-max-tokens", type=int, default=4096,
                   dest="judge_max_tokens",
                   help="Max output tokens for judge responses (increase if reasoning truncates)")

    return p.parse_args()


def bias_check(args: argparse.Namespace) -> None:
    """Check for model-prediction bias across domain and popularity slices.

    Reads the aggregate_report.json (produced by the evaluate step),
    computes max metric disparity across slices, and fails if any
    disparity exceeds the configured thresholds.
    """
    from src.utils.config import (
        BIAS_MAX_ACCURACY_DISPARITY,
        BIAS_MAX_JUDGE_DISPARITY,
    )

    output_dir = Path(args.output_dir)
    report_path = output_dir / "aggregate_report.json"

    if not report_path.exists():
        print("[bias_check] ERROR: aggregate_report.json not found. Run 'evaluate' step first.")
        sys.exit(1)

    report = json.loads(report_path.read_text(encoding="utf-8"))

    violations = []

    # Check domain bias
    by_domain = report.get("by_domain", {})
    if len(by_domain) >= 2:
        # Classification disparity
        cls_accs = []
        for dom, data in by_domain.items():
            cls = data.get("classification")
            if cls and cls.get("n", 0) >= 3:
                cls_accs.append(cls["predecessor_strict"])
        if len(cls_accs) >= 2:
            disparity = max(cls_accs) - min(cls_accs)
            print(f"  Domain accuracy disparity: {disparity:.4f} (threshold: {BIAS_MAX_ACCURACY_DISPARITY})")
            if disparity > BIAS_MAX_ACCURACY_DISPARITY:
                violations.append(f"Domain accuracy disparity {disparity:.4f} > {BIAS_MAX_ACCURACY_DISPARITY}")

        # Judge disparity
        judge_scores = []
        for dom, data in by_domain.items():
            judge = data.get("judge")
            if judge and judge.get("n", 0) >= 3 and judge.get("judge_overall") is not None:
                judge_scores.append(judge["judge_overall"])
        if len(judge_scores) >= 2:
            disparity = max(judge_scores) - min(judge_scores)
            print(f"  Domain judge disparity: {disparity:.4f} (threshold: {BIAS_MAX_JUDGE_DISPARITY})")
            if disparity > BIAS_MAX_JUDGE_DISPARITY:
                violations.append(f"Domain judge disparity {disparity:.4f} > {BIAS_MAX_JUDGE_DISPARITY}")

    # Check popularity/citation-tier bias
    by_tier = report.get("by_citation_tier", {})
    if len(by_tier) >= 2:
        cls_accs = []
        for tier, data in by_tier.items():
            cls = data.get("classification")
            if cls and cls.get("n", 0) >= 3:
                cls_accs.append(cls["predecessor_strict"])
        if len(cls_accs) >= 2:
            disparity = max(cls_accs) - min(cls_accs)
            print(f"  Popularity accuracy disparity: {disparity:.4f} (threshold: {BIAS_MAX_ACCURACY_DISPARITY})")
            if disparity > BIAS_MAX_ACCURACY_DISPARITY:
                violations.append(f"Popularity accuracy disparity {disparity:.4f} > {BIAS_MAX_ACCURACY_DISPARITY}")

        judge_scores = []
        for tier, data in by_tier.items():
            judge = data.get("judge")
            if judge and judge.get("n", 0) >= 3 and judge.get("judge_overall") is not None:
                judge_scores.append(judge["judge_overall"])
        if len(judge_scores) >= 2:
            disparity = max(judge_scores) - min(judge_scores)
            print(f"  Popularity judge disparity: {disparity:.4f} (threshold: {BIAS_MAX_JUDGE_DISPARITY})")
            if disparity > BIAS_MAX_JUDGE_DISPARITY:
                violations.append(f"Popularity judge disparity {disparity:.4f} > {BIAS_MAX_JUDGE_DISPARITY}")

    # Write bias report
    bias_report = {
        "passed": len(violations) == 0,
        "violations": violations,
        "n_domains": len(by_domain),
        "n_tiers": len(by_tier),
    }
    bias_path = output_dir / "bias_report.json"
    bias_path.write_text(json.dumps(bias_report, indent=2), encoding="utf-8")

    # Log to MLflow if available
    try:
        from src.mlflow_utils import log_bias_report as _log_bias

        flat_metrics = {}
        for dom, data in by_domain.items():
            cls = data.get("classification")
            if cls:
                flat_metrics[f"bias_domain_{dom}_accuracy"] = cls.get("predecessor_strict", 0.0)
        for tier, data in by_tier.items():
            cls = data.get("classification")
            if cls:
                flat_metrics[f"bias_tier_{tier}_accuracy"] = cls.get("predecessor_strict", 0.0)

        _log_bias(
            bias_metrics=flat_metrics,
            model_version=report.get("generated_at", "unknown"),
            passed=bias_report["passed"],
        )
    except Exception as exc:
        print(f"  MLflow bias logging skipped: {exc}")

    if violations:
        print(f"\n[bias_check] FAILED — {len(violations)} violation(s):")
        for v in violations:
            print(f"  - {v}")
        sys.exit(1)
    else:
        print("[bias_check] PASSED — no bias threshold violations detected.")


if __name__ == "__main__":
    args = _parse_args()
    dispatch = {
        "run_inference": run_inference,
        "evaluate":      evaluate,
        "upload":        upload,
        "bias_check":    bias_check,
    }
    dispatch[args.step](args)
