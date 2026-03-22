"""
Structured JSON Logger for JobClaw.

Provides consistent, machine-parseable log output across all scrapers.
Logs to both console (human-readable) and file (JSON for log aggregators).

Usage:
    from scripts.utils.logger import get_logger, _log
    log = get_logger("scrape_ats")
    log.info("Starting scraper", companies=500, shard=2)

    # Legacy compat — _log() still works everywhere
    _log("Some message", "INFO", "ingestor")
"""

import json
import logging
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)

JSON_LOG_FILE = LOGS_DIR / "jobclaw.jsonl"
TEXT_LOG_FILE = LOGS_DIR / "jobclaw.log"

_log_lock = threading.Lock()


# ── Legacy _log() — backward compatible ───────────────────────────────


def _log(msg: str, level: str = "INFO", tag: str = "ingestor") -> None:
    """Legacy log function — writes to console + system.log."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"{ts} | {level} | [{tag}] {msg}"
    try:
        print(entry)
    except UnicodeEncodeError:
        print(entry.encode("ascii", errors="replace").decode("ascii"))
    with _log_lock, open(LOGS_DIR / "system.log", "a", encoding="utf-8") as f:
        f.write(entry + "\n")


# ── Structured Logger ─────────────────────────────────────────────────


class JSONFormatter(logging.Formatter):
    """Emit structured JSON log lines for machine parsing."""

    def format(self, record):
        log_entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if hasattr(record, "_extra"):
            log_entry.update(record._extra)
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


class PrettyFormatter(logging.Formatter):
    """Human-readable console output with colors."""

    COLORS = {
        "DEBUG": "\033[90m",
        "INFO": "\033[36m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }
    RESET = "\033[0m"

    def format(self, record):
        color = self.COLORS.get(record.levelname, "")
        ts = datetime.now().strftime("%H:%M:%S")
        prefix = f"{color}{ts} [{record.levelname[0]}]{self.RESET}"
        msg = record.getMessage()
        if hasattr(record, "_extra"):
            extras = " ".join(f"{k}={v}" for k, v in record._extra.items())
            if extras:
                msg = f"{msg}  {color}|{self.RESET} {extras}"
        return f"{prefix} {record.name}: {msg}"


class StructuredLogger(logging.Logger):
    """Logger that accepts keyword arguments as structured fields."""

    def _log_with_extras(self, level, msg, kwargs):
        exc_info = kwargs.pop("exc_info", None)
        record = self.makeRecord(self.name, level, "(unknown)", 0, msg, (), exc_info)
        record._extra = kwargs
        self.handle(record)

    def info(self, msg, **kwargs):
        if self.isEnabledFor(logging.INFO):
            self._log_with_extras(logging.INFO, msg, kwargs)

    def warning(self, msg, **kwargs):
        if self.isEnabledFor(logging.WARNING):
            self._log_with_extras(logging.WARNING, msg, kwargs)

    def error(self, msg, **kwargs):
        if self.isEnabledFor(logging.ERROR):
            self._log_with_extras(logging.ERROR, msg, kwargs)

    def debug(self, msg, **kwargs):
        if self.isEnabledFor(logging.DEBUG):
            self._log_with_extras(logging.DEBUG, msg, kwargs)


_initialized = False


def get_logger(name: str = "jobclaw") -> StructuredLogger:
    """Get or create a structured logger with JSON + console output."""
    global _initialized

    logging.setLoggerClass(StructuredLogger)
    logger = logging.getLogger(name)

    if not _initialized:
        logger.setLevel(logging.DEBUG)

        console = logging.StreamHandler(sys.stdout)
        console.setLevel(logging.INFO)
        console.setFormatter(PrettyFormatter())
        logger.addHandler(console)

        json_handler = logging.FileHandler(JSON_LOG_FILE, encoding="utf-8")
        json_handler.setLevel(logging.DEBUG)
        json_handler.setFormatter(JSONFormatter())
        logger.addHandler(json_handler)

        text_handler = logging.FileHandler(TEXT_LOG_FILE, encoding="utf-8")
        text_handler.setLevel(logging.INFO)
        text_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"))
        logger.addHandler(text_handler)

        _initialized = True

    return logger


class ScrapeTimer:
    """Context manager for timing scraper operations.

    Usage:
        log = get_logger("scrape_ats")
        with ScrapeTimer(log, "greenhouse", companies=500):
            await scrape_greenhouse()
    """

    def __init__(self, logger, operation: str, **extra):
        self.logger = logger
        self.operation = operation
        self.extra = extra
        self.start = None

    def __enter__(self):
        self.start = time.perf_counter()
        self.logger.info(f"Starting {self.operation}", **self.extra)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = round(time.perf_counter() - self.start, 2)
        if exc_type:
            self.logger.error(
                f"Failed {self.operation}",
                duration_s=elapsed,
                error=str(exc_val),
                **self.extra,
            )
        else:
            self.logger.info(
                f"Completed {self.operation}",
                duration_s=elapsed,
                **self.extra,
            )
        return False
