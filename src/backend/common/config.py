"""
common/config.py
----------------
Single source of truth for all settings shared across pred_successor_view
and evolution_view.
"""

import os
import logging
from datetime import datetime
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
    "paperId,title,year,citationCount,influentialCitationCount"
)

# Fields requested by evolution_view (full)
S2_PAPER_FIELDS_FULL = (
    "paperId,externalIds,title,abstract,year,"
    "citationCount,influentialCitationCount,"
    "fieldsOfStudy,s2FieldsOfStudy,"
    "tldr,openAccessPdf,authors"
)

S2_REFERENCE_FIELDS_MINIMAL = (
    "citedPaper.paperId,citedPaper.title,citedPaper.year,"
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
    "citingPaper.paperId,citingPaper.title,citingPaper.year,"
    "citingPaper.citationCount,intents,isInfluential"
)

# ---------------------------------------------------------------------------
# Gemini (evolution_view only)
# ---------------------------------------------------------------------------

GEMINI_API_KEY          = os.environ.get("GEMINI_API_KEY")
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
LOG_DIR = "logs"


def get_logger(name: str = "research_lineage") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        logger.propagate = False

        fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-5s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )

        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(fmt)
        logger.addHandler(ch)

        os.makedirs(LOG_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fh = logging.FileHandler(
            os.path.join(LOG_DIR, f"{name}_{ts}.log"), encoding="utf-8"
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    return logger


logger = get_logger("backend")


def log_event(tag: str, **kwargs) -> None:
    """Emit a structured analytics log line parseable by GCP Logging / Datadog."""
    pairs = " ".join(f"{k}={v}" for k, v in kwargs.items())
    logger.info("[%s] %s", tag, pairs)
