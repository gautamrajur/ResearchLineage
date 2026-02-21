# ResearchLineage

LLM Powered Research Lineage and Path Tracker — enables users to research in the fastest time possible.

We're not replacing comprehensive literature reviews or deep reading (that's impossible!). We're the Wikipedia of research lineages, a starting point that helps researchers get oriented 10x faster, so they can read the right papers in the right order with the right context. Researchers don't need another tool that replaces reading. They need a tool that makes reading more strategic. We provide the map before the journey.

---

## Test Suite

All tests use **pytest** with configuration in `conftest.py` and `pyproject.toml`. Test packages mirror `src/`: each `tests/unit/<layer>/test_*.py` file exercises the corresponding `src/<layer>/*.py` module.

### Test modules at a glance

| Test package | Covers (`src/`) | Purpose |
|--------------|-----------------|---------|
| `unit/api/` | `api/base`, `api/semantic_scholar`, `api/openalex` | Rate limiting, retries, 429 handling, API client behaviour |
| `unit/cache/` | `cache/` | Redis client (get/set/delete, connection handling) |
| `unit/database/` | `database/`, `tasks/database_write` | Connection, repositories; DatabaseWriteTask (write operations) |
| `unit/storage/` | `storage/` | GCS client (upload/download, buckets) |
| `unit/tasks/` | `tasks/` | PDF fetcher, acquisition, validation, cleaning, citation graph, features, schema, quality, anomaly detection |
| `unit/utils/` | `utils/id_mapper`, `utils/errors` | DOI/ID extraction, custom exception hierarchy |
| `integration/` | — | End-to-end flow: validation → cleaning [→ graph] with fixture data |

### Prerequisites

Install dev dependencies (includes pytest, pytest-cov, pytest-mock, pytest-asyncio):

```bash
poetry install --with dev
```

Or with pip:

```bash
pip install pytest pytest-cov pytest-mock pytest-asyncio
```

### Directory structure

```
tests/
├── conftest.py                       # Path setup, shared fixtures, mocks (GCS, Redis)
├── unit/
│   ├── api/                          # src.api
│   │   ├── test_base.py              # RateLimiter, BaseAPIClient (retry, 429, HTTP)
│   │   ├── test_semantic_scholar.py
│   │   └── test_openalex.py
│   ├── cache/                        # src.cache
│   │   └── test_redis_client.py
│   ├── database/                     # src.database + src.tasks.database_write
│   │   ├── test_connection.py
│   │   ├── test_repositories.py
│   │   └── test_database_write.py    # DatabaseWriteTask (tasks)
│   ├── storage/                      # src.storage
│   │   └── test_gcs_client.py
│   ├── tasks/                        # src.tasks (pipeline stages)
│   │   ├── test_pdf_fetcher.py
│   │   ├── test_data_acquisition.py
│   │   ├── test_data_validation.py
│   │   ├── test_data_cleaning.py
│   │   ├── test_citation_graph.py    # Skipped unless RUN_CITATION_GRAPH_TESTS=1
│   │   ├── test_feature_engineering.py
│   │   ├── test_schema_transformation.py
│   │   ├── test_quality_validation.py
│   │   └── test_anomaly_detection.py
│   └── utils/                        # src.utils
│       ├── test_id_mapper.py
│       └── test_errors.py
└── integration/
    └── test_pipeline_flow.py         # Validation → Cleaning [→ Graph]; graph tests conditional
```

### Conftest: fixtures and mocks

**Shared fixtures** (use in any test via function argument):

| Fixture | Description |
|---------|-------------|
| `sample_paper` | Paper dict: paperId, title, abstract, year, authors, externalIds, venue, etc. |
| `sample_reference` | Reference edge: fromPaperId, toPaperId, isInfluential, contexts, intents |
| `sample_citation` | Citation edge (same shape as reference) |

**Mocks** (no real I/O): `google.cloud.storage` and `redis` are patched so tests run without GCS or Redis. Mock any other external services in the test or conftest.

### Running tests

All commands from **project root**. `pyproject.toml` sets `testpaths = ["tests"]`, so `pytest` and `pytest tests` are equivalent.

**By scope:**

```bash
# All tests
pytest
pytest tests -v

# Unit only / integration only
pytest tests/unit -v
pytest tests/integration -v
```

**By layer (unit):**

```bash
pytest tests/unit/api -v
pytest tests/unit/cache -v
pytest tests/unit/database -v
pytest tests/unit/storage -v
pytest tests/unit/tasks -v
pytest tests/unit/utils -v
```

**By file or test:**

```bash
# Single file
pytest tests/unit/tasks/test_data_validation.py -v

# Single test by node id
pytest tests/unit/api/test_base.py::TestRateLimiter -v

# By name pattern (-k)
pytest tests/unit -k "validation" -v
```

**Excluding paths:**

```bash
pytest tests/unit --ignore=tests/unit/tasks/test_citation_graph.py -v
pytest tests/unit --ignore=tests/unit/database -v
```

### Coverage

```bash
# Terminal report with missing lines
pytest tests/unit --cov=src --cov-report=term-missing

# HTML report (htmlcov/)
pytest tests/unit --cov=src --cov-report=html

# Fail if below threshold
pytest tests/unit --cov=src --cov-fail-under=50
```

### Conditional tests (citation graph)

Tests that run `CitationGraphConstructionTask` or use NetworkX can segfault in some environments (numpy.linalg). They are **skipped unless**:

```bash
RUN_CITATION_GRAPH_TESTS=1 pytest tests/unit -v
RUN_CITATION_GRAPH_TESTS=1 pytest tests/unit/tasks/test_citation_graph.py -v
RUN_CITATION_GRAPH_TESTS=1 pytest tests/integration -v
```

### Useful flags

| Flag | Effect |
|------|--------|
| `-v` / `-vv` | Verbose (one line per test / more detail) |
| `-x` | Stop on first failure |
| `--lf` | Re-run only last failed tests |
| `--tb=short` | Shorter tracebacks |
| `-q` | Quiet |
| `--ignore=path` | Exclude file or directory |
| `-n auto` | Parallel (requires pytest-xdist) |

### Writing new tests

1. **Mirror source** — `src/tasks/data_cleaning.py` → `tests/unit/tasks/test_data_cleaning.py`
2. **Use shared fixtures** — `sample_paper`, `sample_reference`, `sample_citation` from conftest
3. **Mock external I/O** — GCS and Redis are already mocked; patch other services as needed
4. **Name clearly** — e.g. `test_missing_target_paper_id_raises`
5. **Group in classes** — e.g. `TestDataValidationTaskStructure`, `TestRateLimiter`

### Quick reference

| Goal | Command |
|------|--------|
| All tests | `pytest` or `pytest tests -v` |
| Unit only | `pytest tests/unit -v` |
| Integration only | `pytest tests/integration -v` |
| One layer | `pytest tests/unit/tasks -v` |
| One file | `pytest tests/unit/utils/test_errors.py -v` |
| One test | `pytest tests/unit/utils/test_errors.py::test_validation_error -v` |
| With coverage | `pytest tests/unit --cov=src --cov-report=term-missing` |
| Include citation graph | `RUN_CITATION_GRAPH_TESTS=1 pytest tests/unit -v` |
| Stop on first fail | `pytest -x` |
| Re-run failed | `pytest --lf` |
