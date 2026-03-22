"""
config.py - ResearchLineage Pipeline Configuration

All API keys, constants, and settings in one place.
"""

import os

# ========================================
# API Keys
# ========================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyB29armp7xwXRjVXzh7OhSPpyHfy_haqX4")

# Optional — gives higher rate limits on Semantic Scholar
S2_API_KEY = os.environ.get("S2_API_KEY", None)

# ========================================
# Gemini Settings
# ========================================

GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_TEMPERATURE = 0.2
GEMINI_MAX_OUTPUT_TOKENS = 16000

# ========================================
# Pipeline Settings
# ========================================

MAX_DEPTH = 6          # How far back to trace the lineage
MAX_CANDIDATES = 8     # Max methodology papers to send to Gemini per step

# ========================================
# Semantic Scholar API
# ========================================

S2_BASE_URL = "https://api.semanticscholar.org/graph/v1"
S2_REQUEST_TIMEOUT = 30
S2_MAX_RETRIES = 10     # Matches tree view
S2_RETRY_BASE_WAIT = 5  # Matches tree view

# ========================================
# Text Extraction
# ========================================

ARXIV_HTML_URLS = [
    "https://arxiv.org/html/{arxiv_id}",
    "https://ar5iv.labs.arxiv.org/html/{arxiv_id}"
]
UNPAYWALL_EMAIL = "vigneshrb250@email.com" 
HTML_REQUEST_TIMEOUT = 30

# ========================================
# Data Export
# ========================================

INPUT_DIR = "inputs"
OUTPUT_DIR = "outputs"
TRAINING_DATA_FILE = os.path.join(OUTPUT_DIR, "lineage_training_data.jsonl")
TIMELINE_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "timelines")
STATE_FILE = os.path.join(OUTPUT_DIR, "run_state.jsonl")


# ========================================
# Logging
# ========================================

import logging
from datetime import datetime

VERBOSE = True  # Keep for backward compatibility
LOG_DIR = "logs"

def get_logger(name="research_lineage"):
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        logger.propagate = False

        fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-5s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(fmt)
        logger.addHandler(ch)

        os.makedirs(LOG_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = os.path.join(LOG_DIR, f"run_{ts}.log")
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setLevel(logging.INFO)
        fh.setFormatter(fmt)
        logger.addHandler(fh)

        logger.info(f"📄 Logging to: {log_path}")

    return logger

logger = get_logger()
