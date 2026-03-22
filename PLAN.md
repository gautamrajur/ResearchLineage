# CI/CD Pipeline for ResearchLineage — Implementation Plan

## Context

ResearchLineage fine-tunes a Qwen2.5-7B LLM on research citation data using Modal A100s, serves it via vLLM, and evaluates against Gemini foundation models. The rubric (`Model_pipeline.pdf`) requires experiment tracking, bias detection, sensitivity analysis, and a full CI/CD pipeline with automated validation, registry push, notifications, and rollback.

**What already exists:**
- Bias detection: `_detect_bias_via_slicing()` in `src/tasks/quality_validation.py:187-355` (temporal, citation, venue bias) + stratified splitting with domain/popularity in `src/tasks/lineage_pipeline.py:1078-1768`
- Training code on `training_vignesh` branch (Modal-based Qwen2.5-7B)
- Evaluation code on `llm-eval-dag/jithin` branch (classification, LLM judge, semantic)
- Unit tests with 171 tests including 21 for bias detection
- Docker test runner (`Dockerfile.test`)

**What's missing:**
- CI/CD pipeline (no GitHub Actions)
- Experiment tracking (no MLflow)
- Model registry (GCS only, no Artifact Registry)
- Rollback mechanism
- Notifications for pipeline failures
- Model-prediction-level bias analysis (existing bias is data-level only)

**What's NOT applicable (LLM context):**
- Hyperparameter tuning / sensitivity analysis — rubric exempts pre-trained large models: *"some of these steps might not be necessary (e.g., model training or hyperparameter tuning)"*
- Training is rare/one-time — CI/CD training workflow is manual-dispatch only

---

## Phase 0: Branch Setup & Code Consolidation

Create `feature/cicd-pipeline` from `main`. Merge in code from two branches:

**From `training_vignesh`:**
- `dags/training_dag.py`
- `scripts/modal_train.py`, `scripts/modal_serve.py`
- `docker/training.Dockerfile`, `docker/requirements-training.txt`

**From `llm-eval-dag/jithin`:**
- `dags/evaluate_performance.py`
- `src/evaluation/` (entire directory — pipeline.py, config.py, types.py, model_client.py, gcs_utils.py, evaluators/)
- `src/tasks/evaluation_task.py`

Resolve conflicts in `docker-compose.yml`, `pyproject.toml`, `src/utils/config.py`.

---

## Phase 1: MLflow Integration

**Satisfies rubric:** Experiment Tracking (§4), Model Development (§2)

### 1.1 Add MLflow to `docker-compose.yml`
- `mlflow-db`: Postgres 15 container (port 5434, volume `mlflow_metadata`)
- `mlflow`: MLflow server (`ghcr.io/mlflow/mlflow:v2.16.0`)
  - Backend: `postgresql+psycopg2://...@mlflow-db:5432/mlflow`
  - Artifact root: `gs://researchlineage-data/mlflow-artifacts`
  - Expose port 5001
- Add `MLFLOW_TRACKING_URI=http://mlflow:5001` to Airflow service environments

### 1.2 Add `mlflow>=2.16.0` to `pyproject.toml`

### 1.3 Create `src/mlflow_utils.py`
- `get_or_create_experiment(name)` → experiment ID
- `log_training_run(params, metrics, model_uri, tags)` → run_id
- `log_evaluation_run(eval_report, model_version, tags)` → run_id
- `log_bias_report(bias_report, model_version)` → run_id
- `register_model(run_id, model_name, model_uri)` → ModelVersion
- `get_latest_production_model(model_name)` → ModelVersion

### 1.4 Add `log_to_mlflow` task to `dags/training_dag.py`
- Runs after training, reads metrics JSON from GCS, logs to MLflow

### 1.5 Add MLflow logging to `src/evaluation/pipeline.py`
- Log aggregate metrics (classification, judge, semantic) after each eval run

---

## Phase 2: Model-Prediction Bias Analysis (Lightweight)

**Satisfies rubric:** Bias Detection (§5, §6) — specifically the **model output** bias requirement

**What already exists (DO NOT duplicate):**
- Data-level bias: `src/tasks/quality_validation.py:187-355` — `_detect_bias_via_slicing()` handles temporal, citation, venue bias on the dataset
- Split-level bias mitigation: `src/tasks/lineage_pipeline.py:1078-1768` — stratified splitting by domain × popularity tiers
- Tests: `tests/unit/tasks/test_quality_validation.py:78-98`

**What's new (thin wrapper only):**
The rubric requires checking if the **model's predictions** are biased across slices — not just the data. The eval branch already computes per-sample metrics. We need a lightweight function that:

### 2.1 Add `slice_and_report()` to existing `src/evaluation/pipeline.py`
- Takes per-sample eval results + paper metadata
- Reuses the **existing** popularity tiers from `lineage_pipeline.py:1689-1708` (`_assign_popularity_tiers`)
- Reuses the **existing** domain classification from paper metadata
- Groups eval metrics (predecessor_accuracy, judge_overall_mean, semantic_overall_mean) by slice
- Computes max disparity across slices
- Returns pass/fail based on thresholds (max disparity ≤ 0.15)

This is ~50-80 lines of code, NOT a new module. It reuses existing slicing logic and existing eval metrics.

### 2.2 Add `bias_check` task to `dags/evaluate_performance.py`
- Runs after `evaluate`, calls `slice_and_report()`, logs to MLflow
- DAG flow: `run_inference >> evaluate >> [upload_to_gcs, bias_check]`

### 2.3 Wire existing data-level bias into CI
- The existing `_detect_bias_via_slicing()` from `quality_validation.py` already runs in DAG 1
- CI/CD just needs to verify it passes — no new code, just a GitHub Actions step that checks the quality report

---

## Phase 3: Model Registry & Rollback

**Satisfies rubric:** Artifact Registry Push (§2.6, §8.7), Rollback (§7.6)

### 3.1 Create `src/registry/artifact_registry.py`
- `push_model_to_registry(model_gcs_uri, version, metadata)` → registry path
- `list_model_versions(model_name)` → version list with metadata
- `promote_model(model_name, version, stage)` → mark production/staging

### 3.2 Create `src/registry/rollback.py`
- `rollback_model(target_version)` → updates `pipeline_state.json` on GCS, redeploys to Modal
- `get_rollback_candidates()` → previous versions from MLflow/pipeline_state

### 3.3 Add `google-cloud-artifact-registry>=1.11.0` to `pyproject.toml`

---

## Phase 4: GitHub Actions Workflows

**Satisfies rubric:** CI/CD Pipeline Automation (§7)

### 4.1 `.github/workflows/ci.yml` — On every push/PR
| Job | What it does |
|-----|-------------|
| **lint** | `ruff check . && ruff format --check .` |
| **typecheck** | `mypy src/ --ignore-missing-imports` |
| **test** | Build `Dockerfile.test`, run `pytest tests/ -v -m unit` |
| **dag-validation** | `python scripts/validate_dags.py` (imports each DAG, checks for cycles) |

### 4.2 Create `scripts/validate_dags.py`
- Imports each DAG file, verifies DAG object created, no import errors, no cycles

### 4.3 `.github/workflows/model-evaluation.yml` — On eval code changes + manual dispatch
- **Trigger**: push to main changing `src/evaluation/**`, `dags/evaluate_performance.py`
- **evaluate**: Run eval pipeline against canary eval set on GCS
- **bias-gate**: Run `slice_and_report()` on results, fail if disparity exceeds thresholds
- **threshold-gate**: Fail if metrics below thresholds (predecessor_accuracy≥0.60, judge≥3.0, semantic≥0.65)
- **Secrets**: `GCP_SA_KEY`, `EVAL_MODEL_ENDPOINT`

### 4.4 `.github/workflows/model-training.yml` — Manual dispatch only
- **Inputs**: `model_version`, `min_new_samples` (default 50), `skip_eval` (bool)
- **Jobs**: train (Modal) → log-mlflow → evaluate → bias-check → register (Artifact Registry + MLflow Model Registry)
- **Secrets**: `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET`, `GCP_SA_KEY`

### 4.5 `.github/workflows/deploy.yml` — After all checks pass
- **deploy**: `modal deploy scripts/modal_serve.py` with new model version
- **smoke-test**: Send test request, verify valid JSON response
- **update-state**: Update `pipeline_state.json` on GCS

### 4.6 `.github/workflows/rollback.yml` — Manual dispatch
- **Input**: `target_version`
- **rollback**: Call `src/registry/rollback.py`
- **verify**: Smoke test rolled-back endpoint
- **notify**: Alert team about rollback

---

## Phase 5: Notifications

**Satisfies rubric:** Notifications and Alerts (§7.5)

### 5.1 Add Slack/email notifications to all workflows
- Use `slackapi/slack-github-action@v1.26` in `if: always()` blocks
- Red alert on failure, green on deploy success
- Secret: `SLACK_WEBHOOK_URL`
- Fallback: reuse existing `src/utils/email_service.py` for email alerts

### 5.2 Create `scripts/notify.py`
- CLI: `python scripts/notify.py --channel slack --event training_complete --status success`
- Supports both Slack webhook and email

---

## Phase 6: Dependency & Docker Updates

### 6.1 Update `pyproject.toml`
- Add `mlflow>=2.16.0`, `google-cloud-artifact-registry>=1.11.0`

### 6.2 Update `docker/airflow.Dockerfile`
- Add `mlflow` to pip install (so Airflow tasks can log to MLflow)

### 6.3 `Dockerfile.test` — NO CHANGES
- Unit tests mock external deps (MLflow, GCS, Modal)
- Existing deps (pytest, networkx, pandas) sufficient for all unit tests
- No new pip packages needed in the test container

---

## New Files to Create

```
.github/workflows/ci.yml
.github/workflows/model-training.yml
.github/workflows/model-evaluation.yml
.github/workflows/deploy.yml
.github/workflows/rollback.yml
src/mlflow_utils.py
src/registry/__init__.py
src/registry/artifact_registry.py
src/registry/rollback.py
scripts/validate_dags.py
scripts/notify.py
tests/unit/test_mlflow_utils.py
tests/unit/test_registry.py
```

## Files to Modify

```
docker-compose.yml              — add mlflow + mlflow-db services
pyproject.toml                  — add mlflow, google-cloud-artifact-registry
docker/airflow.Dockerfile       — add mlflow to pip install
src/utils/config.py             — add MLflow tracking URI, bias thresholds
src/evaluation/pipeline.py      — add slice_and_report() + MLflow logging
dags/training_dag.py            — add log_to_mlflow task
dags/evaluate_performance.py    — add bias_check task
```

---

## Rubric Coverage Matrix

| Rubric Section | Covered By |
|---|---|
| §2 Model Dev & ML Code | Phase 0 (merge training code), Phase 1 (MLflow), Phase 3 (registry) |
| §3 Hyperparameter Tuning | N/A for LLM — rubric exempts pre-trained models. LoRA config documented in modal_train.py |
| §4 Experiment Tracking | Phase 1 (MLflow — params, metrics, model versions per run) |
| §5 Sensitivity Analysis | N/A for LLM — rubric exempts pre-trained models |
| §6 Bias Detection (Slicing) | **Already exists** in quality_validation.py + lineage_pipeline.py (data-level). Phase 2 adds model-prediction bias (lightweight). CI/CD wires both into automated checks |
| §7 CI/CD Automation | Phase 4 (5 GitHub Actions workflows), Phase 5 (notifications) |
| §7.6 Rollback | Phase 3 (rollback.py + rollback.yml workflow) |
| §8 Code Implementation | All phases (Dockerized, data loading, training, validation, bias, registry) |

---

## Verification

1. **Phase 0**: `python -c "import dags.training_dag; import dags.evaluate_performance"` — no import errors
2. **Phase 1**: `docker-compose up mlflow mlflow-db` → MLflow UI at localhost:5001; log dummy experiment
3. **Phase 2**: Run eval pipeline, verify `slice_and_report()` produces per-slice metrics matching existing quality_validation patterns
4. **Phase 3**: Test model push to Artifact Registry; test rollback with mock Modal deploy
5. **Phase 4**: Push to feature branch → all workflows trigger; test threshold gates pass/fail
6. **Phase 5**: Trigger failing workflow → verify notification arrives

---

## Implementation Order

```
Phase 0 (branch setup)
  → Phase 1 + 6 in parallel (MLflow + dependency updates)
  → Phase 2 (model-prediction bias — lightweight, reuses existing)
  → Phase 3 (registry + rollback)
  → Phase 4 (GitHub Actions — depends on all modules being ready)
  → Phase 5 (notifications — added to workflows)
```
