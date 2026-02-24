# ResearchLineage — LLM-Powered Research Lineage & Path Tracker

> *"We're not replacing comprehensive literature reviews. We're the Wikipedia of research lineages — a starting point that helps researchers get oriented 10x faster, so they can read the right papers in the right order with the right context."*

Given a seed paper ID, this pipeline crawls the Semantic Scholar citation graph, validates and cleans the data, builds a directed citation network, engineers influence features, detects anomalies and sends email alerts, and writes structured results to a PostgreSQL database — all orchestrated by Apache Airflow.

---

## Table of Contents

1. [Architecture](#architecture)
2. [Project Structure](#project-structure)
3. [Prerequisites](#prerequisites)
4. [Setup](#setup)
5. [Running the Pipeline](#running-the-pipeline)
6. [Running Tests](#running-tests)
7. [Alerting](#alerting)
8. [Logging](#logging)
9. [Data Versioning (DVC)](#data-versioning-dvc)
10. [Configuration Reference](#configuration-reference)
11. [DAGs](#dags)

---

## Architecture

The main pipeline (`research_lineage_pipeline`) is a 10-task Airflow DAG that runs sequentially:

```
[T1] Data Acquisition          — Semantic Scholar API crawl (async, depth-limited BFS)
        ↓
[T2] Data Validation           — Schema checks, type validation, 10% error-rate threshold
        ↓
[T3] Data Cleaning             — Deduplication, self-citation removal, venue normalisation
        ↓
[T4] Citation Graph Construction — NetworkX DiGraph, centrality metrics, connected components
        ↓
[T5] Feature Engineering       — Influence score, temporal category, citation velocity, recency
        ↓
[T6] Schema Transformation     — Flatten to relational tables (papers / authors / citations)
        ↓
[T7] Quality Validation        — Referential integrity, statistical checks, bias detection (85% threshold)
        ↓
[T8] Anomaly Detection         — Z-score outliers, missing data, self-citations + email alert
        ↓
[T9] Database Write            — Upsert to Cloud SQL (PostgreSQL) via Cloud SQL Auth Proxy
```

Inter-task data is passed through Airflow **XCom**. The NetworkX graph object is not serialised; only the derived metrics are pushed downstream.

### Bias Detection

`QualityValidationTask` actively checks for three bias dimensions before allowing data through:

| Dimension | Check | Threshold |
|---|---|---|
| **Temporal** | No single era > 50% of papers | 5 eras: pre-2000, 2000–2010, 2010–2015, 2015–2020, 2020+ |
| **Citation** | Distribution across high/medium/low cited papers | Flags if >70% high-citation |
| **Venue** | No single venue type > 60% | top-conference, arXiv, journal |

If the overall quality score drops below **85%**, the pipeline raises `DataQualityError` and halts before writing to the database.

### Error Handling

Each task raises typed exceptions from `src/utils/errors.py`:

| Exception | Raised by | Condition |
|---|---|---|
| `ValidationError` | T2, T1 | Missing required fields, invalid types, >10% error rate |
| `DataQualityError` | T7 | Quality score below 85% threshold |
| `APIError` | T1 | Semantic Scholar / OpenAlex request failure |
| `RateLimitError` | T1 | API rate limit exceeded |

All exceptions propagate to Airflow which retries the task up to 3 times with a 5-minute delay.

---

## Project Structure

```
.
├── dags/
│   ├── research_lineage_pipeline.py   # Main 10-task citation pipeline DAG
│   └── fine_tuning_data_pipeline.py   # Fine-tuning data generation DAG
│
├── src/
│   ├── api/
│   │   ├── semantic_scholar.py        # Async S2 client with retry/backoff
│   │   ├── openalex.py                # OpenAlex enrichment client
│   │   └── base.py                    # Base HTTP client
│   ├── cache/
│   │   └── redis_client.py            # Redis-based request cache (TTL=48h)
│   ├── database/
│   │   ├── connection.py              # SQLAlchemy engine + session factory
│   │   └── repositories.py            # Upsert helpers for each table
│   ├── tasks/                         # One class per pipeline task
│   │   ├── data_acquisition.py        # T1 — async BFS crawl
│   │   ├── data_validation.py         # T2 — schema + type validation
│   │   ├── data_cleaning.py           # T3 — dedup, normalise
│   │   ├── citation_graph_construction.py  # T4 — NetworkX graph
│   │   ├── feature_engineering.py     # T5 — derived features
│   │   ├── schema_transformation.py   # T6 — flatten to tables
│   │   ├── quality_validation.py      # T7 — quality + bias checks
│   │   ├── anomaly_detection.py       # T8 — statistical anomaly detection + email alert
│   │   ├── database_write.py          # T9 — PostgreSQL upsert
│   │   └── lineage_pipeline.py        # Fine-tuning pipeline helper
│   └── utils/
│       ├── config.py                  # Pydantic BaseSettings (reads .env)
│       ├── errors.py                  # ValidationError, DataQualityError, APIError
│       ├── id_mapper.py               # S2 ↔ ArXiv ID mapping
│       ├── logging.py                 # Centralised logging — single get_logger entry point
│       └── email_service.py           # SMTP email alert service
│
├── tests/
│   ├── conftest.py                    # Shared factory helpers (make_paper, make_ref, make_cit)
│   ├── unit/
│   │   ├── conftest.py                # Per-task input fixtures
│   │   ├── test_data_acquisition.py   # 29 tests (all external deps mocked)
│   │   ├── test_data_validation.py    # 21 tests
│   │   ├── test_data_cleaning.py      # 18 tests
│   │   ├── test_citation_graph.py     # 18 tests
│   │   ├── test_feature_engineering.py  # 16 tests
│   │   ├── test_schema_transformation.py # 17 tests
│   │   ├── test_quality_validation.py # 21 tests
│   │   └── test_anomaly_detection.py  # 14 tests
│   └── integration/
│       ├── conftest.py                # Full pipeline chain fixture (Tasks 2–9, no live APIs)
│       └── test_pipeline_e2e.py       # 18 end-to-end tests
│
├── docker/
│   └── airflow.Dockerfile             # Airflow image with project deps
├── Dockerfile.test                    # Lightweight image for running tests only
├── docker-compose.yml                 # Postgres + Redis + Cloud SQL Proxy + Airflow
├── pyproject.toml                     # Dependencies (Poetry) + pytest config
├── .env.example                       # Template for all required environment variables
└── .dvc/                              # DVC configuration
```

---

## Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| Docker Desktop | ≥ 4.x | Running all services |
| Docker Compose | ≥ v2 | Orchestrating containers |
| Python | 3.11.x | Local development / test runs |
| Poetry | ≥ 2.0 | Dependency management |
| DVC | ≥ 3.x | Data versioning |
| GCP account | — | Cloud SQL + GCS (production only) |

---

## Setup

### 1. Clone and configure environment

```bash
git clone https://github.com/gautamrajur/ResearchLineage.git
cd Datapipeline_Jithin_Shivram

cp .env.example .env
```

Edit `.env` and fill in your credentials (see [Configuration Reference](#configuration-reference) for all options):

```bash
# Minimum required to run the pipeline
SEMANTIC_SCHOLAR_API_KEY=your_s2_api_key_here

# Required for fine-tuning DAG
GEMINI_API_KEY=your_gemini_api_key_here

# GCP path — set to your local gcloud config directory
# Mac/Linux: /Users/<username>/.config/gcloud
# Windows:   C:/Users/<username>/AppData/Roaming/gcloud
GCLOUD_CONFIG_DIR=/Users/your-username/.config/gcloud

# Optional: SMTP alerts on anomaly detection
SMTP_USER=your.email@gmail.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx   # Gmail App Password
ALERT_EMAIL_FROM=your.email@gmail.com
ALERT_EMAIL_TO=alerts@yourdomain.com
```

A free Semantic Scholar API key gives you 100 req/s (vs 1 req/s unauthenticated).

### 2. Install dependencies (local development)

```bash
poetry install --with dev
```

---

## Running the Pipeline

### Start all services

```bash
docker compose up --build -d
```

This starts:
- **Postgres** (`:5433`) — Airflow metadata database
- **Redis** (`:6379`) — API response cache (48h TTL)
- **Cloud SQL Proxy** (`:5432`) — GCP Cloud SQL tunnel (requires `GCLOUD_CONFIG_DIR`)
- **Airflow webserver** (`:8080`) — UI + REST API
- **Airflow scheduler** — DAG execution engine

### Initialise Airflow (first run only)

```bash
docker compose run --rm airflow-init
```

Creates the metadata schema and default admin user:
- URL: http://localhost:8080
- Username: `admin` / Password: `admin`

### Trigger the main pipeline

1. Open http://localhost:8080
2. Find `research_lineage_pipeline` and toggle it **on**
3. Click **Trigger DAG w/ config** and provide:

```json
{
  "paper_id": "204e3073870fae3d05bcbc2f6a8e263d9b72e776",
  "max_depth": 2,
  "direction": "backward"
}
```

`paper_id` is the Semantic Scholar paper ID — the default above is "Attention Is All You Need".
Start with `max_depth: 2` and `direction: backward` for a faster first run.

`direction` options: `backward` (references only), `forward` (citations only), `both`.

**Retries:** 3 attempts per task, 5-minute delay, 60-minute execution timeout.

### Stop all services

```bash
docker compose down
```

---

## Running Tests

Tests are fully isolated — no live API calls, no database connections required.

### Option A: Docker (recommended)

```bash
docker build -f Dockerfile.test -t researchlineage-tests .

# Run with HTML report output
docker run --rm -v $(pwd)/reports:/app/reports researchlineage-tests
```

Open `reports/report.html` in a browser to see the full results dashboard.

Expected result: **171 passed, 1 warning**

The warning is a harmless Pydantic v2 deprecation in `src/utils/config.py` — does not affect functionality.

### Option B: Local

```bash
poetry run pytest tests/ -v
```

### Test coverage

| File | Tests | Scope |
|---|---|---|
| `test_data_acquisition.py` | 29 | Input/output validation, reference/citation filtering logic |
| `test_data_validation.py` | 21 | Schema checks, 10% error-rate threshold, self-citation removal |
| `test_data_cleaning.py` | 18 | Deduplication, venue normalisation, referential filtering |
| `test_citation_graph.py` | 18 | Graph construction, metrics, edge cases (empty graph) |
| `test_feature_engineering.py` | 16 | Feature completeness, normalisation, temporal categories |
| `test_schema_transformation.py` | 17 | Field mapping, ArXiv ID extraction, author UUID fallback |
| `test_quality_validation.py` | 21 | Bias detection, referential integrity, 85% quality threshold |
| `test_anomaly_detection.py` | 14 | Z-score outliers, duplicates, disconnected nodes |
| `test_pipeline_e2e.py` | 18 | Full Tasks 2–9 chain, data integrity across stages |
| **Total** | **171** | |

---

## Alerting

`AnomalyDetectionTask` (T8) sends an email alert whenever anomalies are detected, via `src/utils/email_service.py`.

**Alert format:**

```
Subject: ResearchLineage Anomaly Alert — 5 issue(s) detected

Anomaly detection found 5 issue(s) in pipeline run.
Target paper: 204e3073870fae3d05bcbc2f6a8e263d9b72e776

Breakdown:
  missing_data.missing_abstracts: 2
  missing_data.missing_venues: 1
  citation_anomalies.duplicate_citations: 1
  disconnected_papers.disconnected_papers: 1

Check the Airflow logs for full details.
```

Alerts are **silently skipped** if SMTP credentials are not configured — the pipeline continues normally.

**Gmail setup:** Enable 2-Step Verification → generate an App Password at `myaccount.google.com/apppasswords` → use the 16-character code as `SMTP_PASSWORD`.

---

## Logging

All logging is centralised through `src/utils/logging.py`. Every module in the project uses the same entry point:

```python
from src.utils.logging import get_logger
logger = get_logger(__name__)
```

The root logger is auto-configured on first import with a consistent format:

```
2026-02-23 14:32:01 | INFO     | src.tasks.data_validation | Starting validation
2026-02-23 14:32:01 | WARNING  | src.tasks.anomaly_detection | Detected 3 anomalies
```

The log level is controlled by `LOG_LEVEL` in `.env` (default: `INFO`). Set to `DEBUG` for verbose output during development.

`fine_tuning_data_pipeline` additionally writes a full `DEBUG`-level log to `src/tasks/pipeline_output/pipeline.log` for post-run inspection.

---

## Data Versioning (DVC)

DVC tracks raw/processed research data and fine-tuning artifacts. All data is stored in GCS. The remote is pre-configured in `.dvc/config` — no additional setup required.

### Remote

The project uses a GCS remote named `gcs`:

```
gs://researchlineage-gcs/dvc-store
```

Authentication uses the same GCP credentials as the rest of the project (`GCLOUD_CONFIG_DIR`).

### Tracked datasets

| DVC pointer | DAG | Contents |
|---|---|---|
| `data/raw.dvc` | `research_lineage_pipeline` | Raw API responses from Semantic Scholar |
| `data/processed.dvc` | `research_lineage_pipeline` | Cleaned, validated, and feature-engineered datasets |
| `src/tasks/pipeline_output/splits.dvc` | `fine_tuning_data_pipeline` | Stratified train / val / test splits (70 / 15 / 15) |
| `src/tasks/pipeline_output/llama_format.dvc` | `fine_tuning_data_pipeline` | Llama chat-format training files and metadata sidecars |

### Pull existing data

```bash
dvc pull
```

### Push new data after a pipeline run

**Research lineage pipeline** (updates `data/raw/` and `data/processed/`):

```bash
dvc add data/raw data/processed
dvc push
git add data/raw.dvc data/processed.dvc
git commit -m "Update research lineage datasets"
```

**Fine-tuning pipeline** (updates `splits/` and `llama_format/`):

```bash
dvc add src/tasks/pipeline_output/splits src/tasks/pipeline_output/llama_format
dvc push
git add src/tasks/pipeline_output/splits.dvc src/tasks/pipeline_output/llama_format.dvc
git commit -m "Track fine-tuning artifacts from pipeline run"
```

### Retrieve data from a specific past run

Each `dvc push` is tied to a git commit via the `.dvc` pointer file. To restore an earlier version:

```bash
# Find the commit where that run was recorded
git log --oneline data/raw.dvc

# Restore the pointer from that commit
git checkout <commit-hash> -- data/raw.dvc

# Pull that exact dataset from GCS
dvc pull data/raw.dvc
```

---

## Configuration Reference

All settings are loaded from `.env` via `src/utils/config.py` (Pydantic `BaseSettings`). Environment variables override `.env` values.

| Variable | Default | Description |
|---|---|---|
| `SEMANTIC_SCHOLAR_API_KEY` | `""` | S2 API key (empty = 1 req/s, key = 100 req/s) |
| `GEMINI_API_KEY` | `""` | Google Gemini key for LLM analysis in fine-tuning DAG |
| `POSTGRES_HOST` | `localhost` | PostgreSQL host |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `POSTGRES_DB` | `research_lineage` | Database name |
| `POSTGRES_USER` | `postgres` | Database user |
| `POSTGRES_PASSWORD` | `postgres` | Database password |
| `REDIS_HOST` | `localhost` | Redis host |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_TTL` | `172800` | Cache TTL in seconds (48 hours) |
| `MAX_CITATION_DEPTH` | `3` | Maximum BFS depth for citation crawl |
| `MAX_PAPERS_PER_LEVEL` | `5` | Papers to follow per depth level |
| `MIN_CITATION_COUNT` | `10` | Minimum citations for a paper to be included |
| `GCS_BUCKET_NAME` | `researchlineage-gcs` | GCS bucket for fine-tuning artifacts |
| `GCS_PROJECT_ID` | `researchlineage` | GCP project ID |
| `GCLOUD_CONFIG_DIR` | — | Path to local gcloud config (used by Cloud SQL Proxy) |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `SMTP_HOST` | `smtp.gmail.com` | SMTP server host |
| `SMTP_PORT` | `587` | SMTP port (TLS) |
| `SMTP_USER` | `""` | SMTP login username |
| `SMTP_PASSWORD` | `""` | SMTP password / Gmail App Password |
| `ALERT_EMAIL_FROM` | `""` | Sender address for anomaly alerts |
| `ALERT_EMAIL_TO` | `""` | Recipient address for anomaly alerts |
| `ENVIRONMENT` | `development` | Runtime environment tag |

---

## DAGs

### `research_lineage_pipeline`

**Trigger:** Manual only (`schedule_interval=None`)

**Config parameters:**
```json
{
  "paper_id": "<Semantic Scholar paper ID>",
  "max_depth": 3,
  "direction": "both"
}
```

**Retries:** 3 attempts, 5-minute delay between retries, 60-minute execution timeout per task.

### `fine_tuning_data_pipeline`

Generates structured Gemini fine-tuning data from research lineage chains.

**Stages:** `seed_generation → batch_run → preprocessing → repair → stratified_split → convert_to_llama_format → pipeline_report → upload_to_gcs`

Output is written to `src/tasks/pipeline_output/` and uploaded to GCS. The train/validation/test split is 70/15/15.
