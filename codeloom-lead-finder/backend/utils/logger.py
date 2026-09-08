"""
backend/utils/logger.py
───────────────────────
Structured, colored console logging used throughout the backend.
Import `get_logger(__name__)` in any module.
"""
import logging
import sys

LOG_FORMAT = "%(asctime)s [%(levelname)-8s] %(name)s — %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    datefmt=DATE_FORMAT,
    handlers=[logging.StreamHandler(sys.stdout)],
)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger with the shared configuration."""
    return logging.getLogger(name)
