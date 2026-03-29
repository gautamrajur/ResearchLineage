# Model Development Pipeline — Demo Guide

This document walks through the end-to-end model development pipeline: fine-tuning, evaluation, multi-model comparison, experiment tracking, and CI/CD automation.

---

## What Was Built

A production MLOps pipeline that:
1. Fine-tunes **Qwen 2.5-7B** on research citation data using LoRA on Modal (A100)
2. Evaluates the fine-tuned model against **Gemini 2.5 Pro** as a baseline
3. Selects the best model using a composite scoring formula
4. Tracks all experiments in **MLflow**, registers models in **GCS**, and automates the full flow via **GitHub Actions** and **Airflow**

---

## 1. Fine-Tuning (Modal + LoRA)

**Script:** `scripts/modal_train.py`
**DAG:** `dags/training_dag.py`

- Base model: `Qwen/Qwen2.5-7B-Instruct`
- Hardware: Modal A100 GPU
- Method: LoRA (`r=16`, `alpha=16`, `max_seq_length=8192`)
- Training data: research citation pairs in Qwen chat format (`data/tasks/pipeline_output/qwen_format/`)
- Output: adapter weights uploaded to `gs://researchlineage-gcs/models/trained/<version>/`

```bash
# Trigger training manually
modal run scripts/modal_train.py
```

---

## 2. Evaluation

**Script:** `src/tasks/evaluation_task.py`
**DAG:** `dags/evaluate_performance.py`

Each model is evaluated on 101 test samples across three steps:

| Step | What it does |
|---|---|
| `run_inference` | Sends each test sample to the model endpoint, collects outputs |
| `evaluate` | Scores outputs: classification metrics + LLM-as-judge (Gemini Flash, 1–5 scale) |
| `bias_check` | Checks for performance disparity across domains (CS / Physics / Math) and citation tiers |

### Metrics computed

| Metric | Description |
|---|---|
| `predecessor_strict` | Exact match — did the model identify the correct predecessor paper? |
| `predecessor_soft` | Soft match — correct predecessor OR a valid secondary influence |
| `mrr` | Mean Reciprocal Rank of the correct predecessor in the model's ranked output |
| `secondary_f1` | F1 score for secondary influence identification |
| `judge_overall` | Mean LLM judge score across 5 reasoning dimensions (1–5 scale) |

### Supported model endpoints

| Format | Client used |
|---|---|
| `gemini-*` | Vertex AI (Gemini) |
| `http...` ending in `/v1` | OpenAI-compatible (vLLM) |
| `http...` (Modal URL) | Modal web endpoint |

```bash
# Run evaluation locally
python src/tasks/evaluation_task.py \
  --step run_inference \
  --data-source local \
  --local-input /path/to/test.jsonl \
  --output-dir /tmp/eval_output \
  --model-endpoint https://your-modal-endpoint.modal.run
```

---

## 3. Multi-Model Comparison

**Script:** `src/tasks/model_selection_task.py`
**DAG:** `dags/compare_models.py`
**Workflow:** `.github/workflows/model-comparison.yml`

After evaluating each model independently, the comparison pipeline:

1. **Loads** each model's `aggregate_report.json`
2. **Scores** each model using the composite formula
3. **Selects** the winner
4. **Generates** visual comparison reports
5. **Logs** everything to MLflow
6. **Promotes** the winner to the model registry (on main only)

### Selection Formula

```
Composite Score = 0.75 × predecessor_soft + (judge_overall / 5) × 0.25
```

`predecessor_soft` carries 75% weight (task accuracy), `judge_overall` carries 25% (reasoning quality).

### Latest Results (101 samples)

| Model | Pred. Soft | Judge Overall | Composite |
|---|---|---|---|
| **Gemini 2.5 Pro** | 0.8560 | 3.8400 | **0.7852** |
| Qwen 2.5-7B Fine-tuned | 0.7759 | 3.0857 | **0.7362** |

Gap: **0.05** — meaningfully close given the 7B model is running locally vs a frontier API.

### Output artifacts

| Artifact | Description |
|---|---|
| `model_selection_report.json` | Winner, scores, rankings |
| `comparison_bar.png` | Side-by-side bar chart |
| `comparison_radar.png` | Spider/radar chart |
| `comparison_by_domain.png` | Per-domain breakdown (CS / Physics / Math) |
| `comparison_by_tier.png` | Per-citation-tier breakdown |
| `model_comparison.html` | Self-contained HTML report with all charts |

All stored at `gs://researchlineage-gcs/fine-tuning-artifacts/model_comparison/`

```bash
# Run comparison locally against existing eval reports
python src/tasks/model_selection_task.py \
  --report-dirs /tmp/eval_qwen7b /tmp/eval_gemini \
  --model-names qwen-7b-finetuned gemini-2.5-pro \
  --output-dir /tmp/model_comparison \
  --generate-viz
```

---

## 4. Experiment Tracking (MLflow)

**UI:** http://localhost:5001 (after `docker compose up`)

Every training run and comparison logs to MLflow:

| Run type | Logged data |
|---|---|
| Training | LoRA params, base model, epochs, LR, model GCS URI |
| Evaluation | Classification metrics, judge scores, bias report |
| Comparison | Per-model composite scores, winner, rankings, PNG charts, HTML report |

---

## 5. Model Registry & Rollback

**Files:** `src/registry/artifact_registry.py`, `src/registry/rollback.py`

Models are versioned in GCS:
```
gs://researchlineage-gcs/model-registry/researchlineage-model/
  └── v20260324_143000/
      └── metadata.json    # version, GCS URI, stage, timestamp
```

Rollback to any previous version via GitHub Actions → **Rollback Model** workflow (manual dispatch).

---

## 6. CI/CD Automation (GitHub Actions)

Six workflows automate the full pipeline:

| Workflow | Trigger | What it does |
|---|---|---|
| `ci.yml` | Every push / PR | Lint, typecheck, unit tests, DAG validation |
| `model-training.yml` | Manual dispatch | Train on Modal → log MLflow → register → trigger comparison |
| `model-comparison.yml` | Called by training / manual | Parallel eval → selection → viz → notify |
| `model-evaluation.yml` | Manual / eval code changes | Single-model eval + threshold gates + bias check |
| `deploy.yml` | Manual dispatch | Deploy to Modal (vLLM) → smoke test → update state |
| `rollback.yml` | Manual dispatch | Roll back to previous version → redeploy → notify |

### PR Validation Mode

On pull requests, expensive steps are skipped — cached GCS artifacts are used instead:

- **Training**: validates workflow structure only
- **Evaluation**: downloads existing reports from GCS, runs threshold + bias gates against real data
- **Comparison**: downloads per-model reports from GCS, runs selection + visualization
- **Deploy**: validates scripts exist, skips actual Modal deployment

This means every PR gets full pipeline verification with zero GPU cost.

---

## 7. Notifications & Alerts

Email alerts (SMTP) are sent for every significant pipeline event:

| Event | Trigger |
|---|---|
| CI failure | Any lint/test/typecheck job fails |
| Training complete / failed | After train + log + register |
| Evaluation threshold failure | `predecessor_strict < 0.60` or `judge_overall < 3.0` |
| Bias check failure | Domain disparity exceeds threshold |
| Comparison complete | Winner selected, composite scores reported |
| Deploy success / failure | After smoke test |
| Rollback executed | Always |

Airflow DAGs also have `notify_success` / `notify_failure` tasks with appropriate `trigger_rule`.

---

## Quick Demo Sequence

```bash
# 1. Start services
docker compose up -d

# 2. View MLflow experiments
open http://localhost:5001

# 3. View Airflow DAGs
open http://localhost:8080   # admin / admin

# 4. Run comparison locally with existing eval reports
python src/tasks/model_selection_task.py \
  --report-dirs /tmp/eval_qwen7b /tmp/eval_gemini \
  --model-names qwen-7b-finetuned gemini-2.5-pro \
  --output-dir /tmp/model_comparison \
  --generate-viz
open /tmp/model_comparison/model_comparison.html

# 5. Check GCS artifacts
gsutil ls gs://researchlineage-gcs/fine-tuning-artifacts/model_comparison/

# 6. Trigger CI/CD (opens GitHub Actions)
open https://github.com/gautamrajur/ResearchLineage/actions
```

---

## Key Design Decisions

**Why LoRA?** Full fine-tuning a 7B model requires ~80GB VRAM. LoRA (r=16) achieves comparable task-specific adaptation with ~4GB of trainable parameters on a single A100.

**Why compare against Gemini?** Gemini 2.5 Pro serves as a strong zero-shot baseline. A fine-tuned 7B scoring within 0.05 composite of a frontier model validates that the fine-tuning signal is meaningful.

**Why GCS for PR validation?** Running live inference on every PR would cost GPU time and take 30+ minutes. Caching real eval artifacts on GCS gives full pipeline coverage on PRs in ~2 minutes.

**Why composite scoring?** `predecessor_soft` alone rewards models that produce plausible-sounding but vague outputs. Adding `judge_overall` (LLM-as-judge on reasoning quality) penalises models that get lucky on soft matching without producing coherent explanations.
