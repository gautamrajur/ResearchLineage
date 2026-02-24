"""Centralised logging configuration for ResearchLineage.

Single entry point for all logging across the project:

    from src.utils.logging import get_logger
    logger = get_logger(__name__)

setup_logging() is called automatically on first import and is safe to call
multiple times — it only configures the root logger once.
"""
import logging
import sys
from typing import Optional

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


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
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
        root.addHandler(handler)

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
