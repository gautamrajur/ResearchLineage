"""Centralised logging configuration for ResearchLineage.

Single entry point for all logging across the project:

    from src.utils.logging import get_logger
    logger = get_logger(__name__)

setup_logging() is called automatically on first import and is safe to call
multiple times — it only configures the root logger once.

Elasticsearch integration: set LOG_JSON_FILE env var to a file path and
Filebeat will ship those structured JSON logs to Elasticsearch.
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

# Fields forwarded from logger.xxx(..., extra={...}) calls
_EXTRA_FIELDS = ("dag_id", "task_id", "run_id", "paper_id", "seed_id", "depth")

_configured = False


class _JsonFormatter(logging.Formatter):
    """Formats log records as newline-delimited JSON for Filebeat / Elasticsearch."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            "@timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "service": "researchlineage",
        }
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        for key in _EXTRA_FIELDS:
            if hasattr(record, key):
                entry[key] = getattr(record, key)
        return json.dumps(entry, ensure_ascii=False)


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

    Args:
        level: Log level override (DEBUG/INFO/WARNING/ERROR).
               Defaults to LOG_LEVEL from settings, falls back to INFO.
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
        # Console handler — existing behaviour
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
        root.addHandler(console)

        # JSON file handler — picked up by Filebeat and shipped to Elasticsearch.
        # Only active when LOG_JSON_FILE env var is set (e.g. inside Docker).
        json_path = _json_log_path()
        if json_path:
            file_handler = logging.FileHandler(json_path, encoding="utf-8")
            file_handler.setFormatter(_JsonFormatter())
            root.addHandler(file_handler)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Get a named logger. Ensures root logging is configured first.

    Args:
        name: Logger name — always pass __name__.

    Returns:
        Logger instance.
    """
    setup_logging()
    return logging.getLogger(name)


# Auto-configure on import so any file using logging.getLogger directly
# also inherits the consistent format via the root logger.
setup_logging()
