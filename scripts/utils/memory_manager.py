"""
Memory Manager for AI Job Agent.

Manages the three memory stores:
  - memory/sessions/session_<timestamp>.md   — per-run session logs
  - memory/checkpoints/system_checkpoint.json — current state + next task
  - memory/summaries/system_summary.md        — architecture status

Design rules:
  - NEVER overwrite checkpoint without reading previous state first
  - Atomic writes (write to .tmp, rename to target) for crash safety
  - All directories auto-created on first use
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Resolve project root (two levels up from scripts/utils/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MEMORY_DIR = PROJECT_ROOT / "memory"
SESSIONS_DIR = MEMORY_DIR / "sessions"
CHECKPOINTS_DIR = MEMORY_DIR / "checkpoints"
SUMMARIES_DIR = MEMORY_DIR / "summaries"
CHECKPOINT_FILE = CHECKPOINTS_DIR / "system_checkpoint.json"
SUMMARY_FILE = SUMMARIES_DIR / "system_summary.md"


def _ensure_dirs() -> None:
    """Create memory directories if they don't exist."""
    for d in (SESSIONS_DIR, CHECKPOINTS_DIR, SUMMARIES_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _atomic_write(path: Path, content: str) -> None:
    """Write content atomically: write to temp file, then rename.

    This ensures a crash mid-write doesn't corrupt the target file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent), suffix=".tmp", prefix=path.stem
    )
    try:
        os.write(fd, content.encode("utf-8"))
        os.close(fd)
        # Windows requires target to not exist for os.rename
        if path.exists():
            path.unlink()
        os.rename(tmp_path, str(path))
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


# ═══════════════════════════════════════════════════════════════════════
# SESSION LOGS
# ═══════════════════════════════════════════════════════════════════════

def create_session_log(
    attempted: str,
    implemented: str,
    files_created: list[str],
    system_status: str,
    continuation_instructions: str,
) -> Path:
    """Write a session log as Markdown.

    Returns:
        Path to the created session file.
    """
    _ensure_dirs()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"session_{ts}.md"
    path = SESSIONS_DIR / filename

    content = f"""# Session Log — {ts}

## What Was Attempted

{attempted}

## What Was Implemented

{implemented}

## Files Created

{chr(10).join(f'- `{f}`' for f in files_created) if files_created else '_None_'}

## Current System Status

{system_status}

## Continuation Instructions

{continuation_instructions}
"""
    _atomic_write(path, content)
    return path


# ═══════════════════════════════════════════════════════════════════════
# CHECKPOINTS
# ═══════════════════════════════════════════════════════════════════════

def load_checkpoint() -> dict[str, Any]:
    """Load current checkpoint. Returns empty dict if none exists or corrupted."""
    _ensure_dirs()
    if not CHECKPOINT_FILE.exists():
        return {}
    try:
        return json.loads(CHECKPOINT_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def update_checkpoint(updates: dict[str, Any]) -> dict[str, Any]:
    """Update checkpoint by merging new values on top of existing state.

    ALWAYS reads the previous checkpoint first (requirement #7).

    Args:
        updates: Dict of fields to merge into checkpoint.

    Returns:
        The merged checkpoint after saving.
    """
    _ensure_dirs()
    previous = load_checkpoint()
    merged = {**previous, **updates}
    merged["last_updated"] = datetime.now(timezone.utc).isoformat()
    _atomic_write(CHECKPOINT_FILE, json.dumps(merged, indent=2))
    return merged


# ═══════════════════════════════════════════════════════════════════════
# SUMMARIES
# ═══════════════════════════════════════════════════════════════════════

def update_summary(
    architecture_status: str,
    completed: list[str],
    pending: list[str],
    continuation_plan: str,
    recovery_instructions: str,
) -> Path:
    """Overwrite system summary with current state.

    Returns:
        Path to the summary file.
    """
    _ensure_dirs()
    ts = datetime.now(timezone.utc).isoformat()

    completed_lines = "\n".join(f"- [x] {c}" for c in completed) if completed else "_None yet._"
    pending_lines = "\n".join(f"- [ ] {p}" for p in pending) if pending else "_All complete._"

    content = f"""# System Summary

_Updated: {ts}_

## Architecture Status

{architecture_status}

## Completed Components

{completed_lines}

## Pending Components

{pending_lines}

## Continuation Plan

{continuation_plan}

## Recovery Instructions

{recovery_instructions}
"""
    _atomic_write(SUMMARY_FILE, content)
    return SUMMARY_FILE


# ═══════════════════════════════════════════════════════════════════════
# RESUME STATE
# ═══════════════════════════════════════════════════════════════════════

def get_resume_state() -> dict[str, Any]:
    """Get the resume state for a new session.

    Returns a dict with:
      - status: current system status
      - next_session: what to execute next
      - last_completed_session: timestamp of last successful session
      - should_resume: bool indicating if there's pending work
    """
    checkpoint = load_checkpoint()
    return {
        "status": checkpoint.get("status", "unknown"),
        "next_session": checkpoint.get("next_session", "setup_environment"),
        "last_completed_session": checkpoint.get("last_completed_session"),
        "should_resume": checkpoint.get("status") not in (None, "production_ready", ""),
        "checkpoint": checkpoint,
    }
