"""Centralized logging configuration for ora-automation API.

Usage:
    from .logging_config import setup_logging
    setup_logging()  # Call once at application startup
"""
from __future__ import annotations

import logging
import sys


def setup_logging(
    level: str = "INFO",
    fmt: str = "%(asctime)s | %(name)s | %(levelname)s | %(message)s",
) -> None:
    """Configure logging for the entire application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        fmt: Log message format
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format=fmt,
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,  # Override any existing configuration
    )

    # Set specific loggers
    logging.getLogger("ora_automation_api").setLevel(log_level)
    logging.getLogger("ora_rd_orchestrator").setLevel(log_level)

    # Quiet noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)
