"""Centralised logging configuration for ResearchLineage.

Single entry point for all logging across the project:

    from src.utils.logging import get_logger
    logger = get_logger(__name__)

setup_logging() is called automatically on first import and is safe to call
multiple times — it only configures the root logger once.

Three runtime environments are detected automatically:

  1. Cloud Run  (K_SERVICE env var set by GCP)
     → JSON to stdout only.  Cloud Logging ingests every stdout line and
       parses the JSON fields (level, logger, message, etc.) as indexed
       attributes you can filter on in Logs Explorer.

  2. Docker / Airflow  (LOG_JSON_FILE env var set via docker-compose)
     → Human-readable to stdout  +  NDJSON to file.
       Filebeat tails the file and ships each line to Elasticsearch/Kibana.

  3. Local dev  (neither env var set)
     → Human-readable to stdout only.  No files written, no external deps.
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Structured context fields callers can attach via logger.info(..., extra={...})
_EXTRA_FIELDS = ("dag_id", "task_id", "run_id", "paper_id", "seed_id", "depth")

_configured = False


class _JsonFormatter(logging.Formatter):
    """Emits one JSON object per line.

    Used in two places:
      - stdout on Cloud Run  (Cloud Logging parses the JSON fields)
      - file handler in Docker  (Filebeat ships each line to Elasticsearch)

    "application" is used instead of "service" to avoid conflicting with
    Filebeat's own ECS service.name object mapping in Elasticsearch.
    """

    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            "@timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "application": "researchlineage",
        }
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        for key in _EXTRA_FIELDS:
            if hasattr(record, key):
                entry[key] = getattr(record, key)
        return json.dumps(entry, ensure_ascii=False)


def _on_cloud_run() -> bool:
    """True when running inside Cloud Run. GCP sets K_SERVICE automatically."""
    return bool(os.getenv("K_SERVICE"))


def _json_log_path() -> Optional[Path]:
    """Return the JSON log file path from LOG_JSON_FILE env var, or None."""
    raw = os.getenv("LOG_JSON_FILE", "").strip()
    if not raw:
        return None
    path = Path(raw)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    except OSError:
        return None


def setup_logging(level: Optional[str] = None) -> None:
    """Configure the root logger. Safe to call multiple times — only runs once.

    Handler selection (mutually exclusive environments):

      Cloud Run   → JSON StreamHandler to stdout
      Docker      → plain StreamHandler to stdout  +  JSON FileHandler
      Local dev   → plain StreamHandler to stdout only
    """
    global _configured
    if _configured:
        return

    if level is None:
        try:
            from src.utils.config import settings
            level = settings.log_level
        except Exception:
            level = "INFO"

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    if not root.handlers:
        if _on_cloud_run():
            # Cloud Run: write JSON to stdout so Cloud Logging indexes the fields.
            # No file handler — containers are ephemeral, no Filebeat sidecar.
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(_JsonFormatter())
            root.addHandler(handler)
        else:
            # Local dev or Docker: human-readable console output.
            console = logging.StreamHandler(sys.stdout)
            console.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
            root.addHandler(console)

            # Docker only: JSON file for Filebeat → Elasticsearch.
            json_path = _json_log_path()
            if json_path:
                file_handler = logging.FileHandler(json_path, encoding="utf-8")
                file_handler.setFormatter(_JsonFormatter())
                root.addHandler(file_handler)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Get a named logger, ensuring root logging is configured first."""
    setup_logging()
    return logging.getLogger(name)


setup_logging()
