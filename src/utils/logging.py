"""Centralised logging configuration for ResearchLineage.

Single entry point for all logging across the project:

    from src.utils.logging import get_logger
    logger = get_logger(__name__)

setup_logging() is called automatically on first import and is safe to call
multiple times — it only configures the root logger once.

Elasticsearch integration: set LOG_JSON_FILE env var to a file path and
Filebeat will ship those structured JSON logs to Elasticsearch.
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

# Fields forwarded from logger.xxx(..., extra={...}) calls
_EXTRA_FIELDS = ("dag_id", "task_id", "run_id", "paper_id", "seed_id", "depth")

# Only these logger namespaces are written to the structured JSON file.
# Airflow internals (airflow.*, celery.*, etc.) are excluded — they belong in
# the Airflow task logs, not in the application observability stream.
_APP_LOGGER_PREFIXES = ("src.", "dags.", "test.")

class _AppLogFilter(logging.Filter):
    """Allow only log records whose logger name starts with an app prefix.

    Prevents Airflow/Celery/SQLAlchemy internal logs from polluting the
    structured JSON file that Filebeat ships to Elasticsearch.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return any(record.name.startswith(p) for p in _APP_LOGGER_PREFIXES)


class _AirflowContextFilter(logging.Filter):
    """Inject Airflow task context fields into every log record.

    Airflow's LocalExecutor sets these env vars in every task subprocess:
        AIRFLOW_CTX_DAG_ID, AIRFLOW_CTX_TASK_ID, AIRFLOW_CTX_DAG_RUN_ID

    Injecting them here means every log line automatically carries dag_id,
    task_id, and run_id without any call-site changes, which populates the
    [RL] Task Execution Activity and [RL] Log Volume by DAG Kibana panels.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "dag_id"):
            record.dag_id = os.getenv("AIRFLOW_CTX_DAG_ID", "")
        if not hasattr(record, "task_id"):
            record.task_id = os.getenv("AIRFLOW_CTX_TASK_ID", "")
        if not hasattr(record, "run_id"):
            record.run_id = os.getenv("AIRFLOW_CTX_DAG_RUN_ID", "")
        return True


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
            val = getattr(record, key, "")
            if val:
                entry[key] = val
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
    """Configure the root logger. Safe to call multiple times.

    Idempotent: console handler added only when root has no handlers; JSON
    FileHandler checked by path so duplicates are never added.  The old
    ``_configured`` flag was removed because Airflow's ``dictConfig`` wipes
    root handlers after DAG-file import, causing the FileHandler to be lost
    in task subprocesses.  Re-running this function on every ``get_logger()``
    call recovers the FileHandler transparently.

    Handler selection (mutually exclusive environments):

      Cloud Run   → JSON StreamHandler to stdout
      Docker      → plain StreamHandler to stdout  +  JSON FileHandler
      Local dev   → plain StreamHandler to stdout only
    """
    if level is None:
        try:
            from src.utils.config import settings
            level = settings.log_level
        except Exception:
            level = "INFO"

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    if not root.handlers:
        # Console handler — only added when no handlers exist (i.e. not inside Airflow).
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
        root.addHandler(console)

    # JSON file handler — always added when LOG_JSON_FILE is set, even when
    # Airflow's task log handlers are already on the root logger.  Without this,
    # the guard above causes the FileHandler to be skipped inside Airflow tasks
    # (LocalExecutor pre-populates root.handlers before any task code runs).
    json_path = _json_log_path()
    if json_path:
        already_present = any(
            isinstance(h, logging.FileHandler)
            and getattr(h, "baseFilename", "") == str(json_path.resolve())
            for h in root.handlers
        )
        if not already_present:
            file_handler = logging.FileHandler(json_path, encoding="utf-8")
            file_handler.setFormatter(_JsonFormatter())
            # Only write src.*/dags.*/test.* logs — keeps Airflow internals out.
            file_handler.addFilter(_AppLogFilter())
            # Auto-stamp every record with the Airflow task context when present.
            file_handler.addFilter(_AirflowContextFilter())
            root.addHandler(file_handler)


def enable_script_logging(script_file: str) -> None:
    """Enable Kibana-bound structured logging for a standalone script.

    Call this inside ``if __name__ == "__main__":`` BEFORE the main function.
    It sets LOG_JSON_FILE (if not already set) so that setup_logging() installs
    the JSON FileHandler that Filebeat ships to Elasticsearch / Kibana.
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

    Args:
        script_file: Pass ``__file__`` — used to locate the project root.
    """
    from pathlib import Path as _Path
    if not os.getenv("LOG_JSON_FILE"):
        root = _Path(script_file).resolve().parent.parent
        # scripts/cli/ is one extra level deep
        if not (root / "src").exists():
            root = root.parent
        json_path = root / "logs" / "app" / "researchlineage.jsonl"
        json_path.parent.mkdir(parents=True, exist_ok=True)
        os.environ["LOG_JSON_FILE"] = str(json_path)
    setup_logging()


def get_logger(name: str) -> logging.Logger:
    """Get a named logger, ensuring root logging is configured first."""
    setup_logging()
    return logging.getLogger(name)


setup_logging()
