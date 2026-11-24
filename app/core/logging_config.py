"""Logging configuration for the application."""

import logging


def configure_logging(level: str = "INFO") -> None:
    """Configure application-wide console logging once."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def get_logger(name: str) -> logging.Logger:
    """Return a logger for an application module."""
    return logging.getLogger(name)
