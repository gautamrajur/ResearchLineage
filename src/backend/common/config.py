"""
common/config.py
----------------
Single source of truth for all settings shared across pred_successor_view
and evolution_view.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[4] / ".env")

# ---------------------------------------------------------------------------
# Database (PostgreSQL via Cloud SQL Proxy)
# ---------------------------------------------------------------------------
# Start proxy before use:
#   ./cloud-sql-proxy researchlineage:us-central1:researchlineage-db --port 5432 &

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://jithin:{pw}@127.0.0.1:5432/researchlineage?options=-csearch_path%3Ddeployment_schema".format(
        pw=os.environ.get("PG_PASSWORD", "jithin")
    ),
)

# ---------------------------------------------------------------------------
# Semantic Scholar API
# ---------------------------------------------------------------------------

S2_BASE_URL       = "https://api.semanticscholar.org/graph/v1"
S2_API_KEY        = os.environ.get("S2_API_KEY") or None
S2_REQUEST_TIMEOUT = 30
S2_MAX_RETRIES    = 30      # constant 2 s wait on 429 → 60 s total budget
S2_RETRY_WAIT     = 2       # seconds (constant, not exponential)
S2_INTER_CALL_SLEEP = 1.2   # polite delay between successful calls

# Fields requested by pred_successor_view (minimal)
S2_PAPER_FIELDS_MINIMAL = (
    "paperId,externalIds,title,year,citationCount,influentialCitationCount"
)

# Fields requested by evolution_view (full)
S2_PAPER_FIELDS_FULL = (
    "paperId,externalIds,title,abstract,year,"
    "citationCount,influentialCitationCount,"
    "fieldsOfStudy,s2FieldsOfStudy,"
    "tldr,openAccessPdf,authors"
)

S2_REFERENCE_FIELDS_MINIMAL = (
    "citedPaper.paperId,citedPaper.externalIds,citedPaper.title,citedPaper.year,"
    "citedPaper.citationCount,isInfluential,intents"
)

S2_REFERENCE_FIELDS_FULL = (
    "citedPaper.paperId,citedPaper.title,"
    "citedPaper.year,citedPaper.citationCount,"
    "citedPaper.externalIds,"
    "citedPaper.abstract,citedPaper.openAccessPdf,"
    "isInfluential,intents,contexts"
)

S2_CITATION_FIELDS = (
    "citingPaper.paperId,citingPaper.externalIds,citingPaper.title,citingPaper.year,"
    "citingPaper.citationCount,intents,isInfluential"
)

# ---------------------------------------------------------------------------
# Gemini — Vertex AI (paid endpoint, no free-tier quota cap)
# ---------------------------------------------------------------------------
# Auth: gcloud auth application-default login  OR  GOOGLE_APPLICATION_CREDENTIALS

GEMINI_API_KEY          = os.environ.get("GEMINI_API_KEY")   # kept for fallback
GEMINI_PROJECT          = os.environ.get("GEMINI_PROJECT", "researchlineage")
GEMINI_LOCATION         = os.environ.get("GEMINI_LOCATION", "us-central1")
GEMINI_MODEL            = "gemini-2.5-pro"
GEMINI_TEMPERATURE      = 0.2
GEMINI_MAX_OUTPUT_TOKENS = 16000

# ---------------------------------------------------------------------------
# Evolution view pipeline settings
# ---------------------------------------------------------------------------

MAX_DEPTH      = 6   # how far back to trace the lineage
MAX_CANDIDATES = 5   # max methodology papers sent to Gemini per step

# ---------------------------------------------------------------------------
# Text extraction (evolution_view)
# ---------------------------------------------------------------------------

ARXIV_HTML_URLS = [
    "https://arxiv.org/html/{arxiv_id}",
    "https://ar5iv.labs.arxiv.org/html/{arxiv_id}",
]
UNPAYWALL_EMAIL      = "vigneshrb250@email.com"
HTML_REQUEST_TIMEOUT = 30

# ---------------------------------------------------------------------------
# Data export (evolution_view)
# ---------------------------------------------------------------------------

OUTPUT_DIR           = "outputs"
TRAINING_DATA_FILE   = os.path.join(OUTPUT_DIR, "lineage_training_data.jsonl")
TIMELINE_OUTPUT_DIR  = os.path.join(OUTPUT_DIR, "timelines")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

VERBOSE = True

# Use the project-wide centralized logger so all backend logs flow through
# the same handler chain (console + JSON file for Filebeat when in Docker).
from src.utils.logging import get_logger  # noqa: E402

logger = get_logger("src.backend")


def log_event(tag: str, **kwargs) -> None:
    """Emit a structured analytics log line parseable by GCP Logging / Datadog."""
    pairs = " ".join(f"{k}={v}" for k, v in kwargs.items())
    logger.info("[%s] %s", tag, pairs)
