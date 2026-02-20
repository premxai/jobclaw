"""
Logging utility for AI Job Agent.

Writes to:
  - logs/system.log      (persistent runtime log)
  - memory/sessions/     (session-specific logs via memory_manager)
  - stdout               (console output)
"""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

# Project root: two levels up from scripts/utils/
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"
SYSTEM_LOG = LOGS_DIR / "system.log"


def get_logger(name: str = "job_agent") -> logging.Logger:
    """Get a configured logger that writes to system.log and stdout.

    Args:
        name: Logger name (used for namespacing).

    Returns:
        Configured logging.Logger instance.
    """
    logger = logging.getLogger(name)

    # Avoid duplicate handlers on repeated calls
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # ── File handler → logs/system.log ────────────────────────────────
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(str(SYSTEM_LOG), encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_fmt = logging.Formatter(
        "%(asctime)s | %(name)-20s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_fmt)
    logger.addHandler(file_handler)

    # ── Console handler → stdout ──────────────────────────────────────
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
    )
    console_handler.setFormatter(console_fmt)
    logger.addHandler(console_handler)

    return logger


def log_session_event(event: str, details: str = "") -> None:
    """Log a timestamped event for the current session.

    This is a convenience wrapper for quick event logging from any script.

    Args:
        event: Short event name (e.g., "agent_started", "scrape_complete").
        details: Optional additional details.
    """
    logger = get_logger("session")
    msg = f"[{event}]"
    if details:
        msg += f" {details}"
    logger.info(msg)
