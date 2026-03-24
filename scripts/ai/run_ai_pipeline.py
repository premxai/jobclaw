"""
AI Post-Processing Pipeline — runs after deep-tier scrape.

Two stages:
  1. Semantic dedup   — find cross-platform duplicate listings,
                        mark lower-quality copies as inactive
  2. Salary backfill  — estimate salary for jobs that don't disclose it
                        (confidence >= 0.5 required to update)

Called automatically by the orchestrator / worker after the deep-tier run.
Can also be run standalone for a one-off pass over recent jobs.
"""

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.logger import _log


async def run_ai_pipeline() -> dict:
    """
    Run the full AI post-processing pipeline.
    Returns a summary dict: {dedup_archived, salary_backfilled, duration_s}
    """
    start = time.time()
    dedup_archived = 0
    salary_backfilled = 0

    # ── Stage 1: Semantic dedup ──────────────────────────────────────────
    try:
        from scripts.ai.dedup import JobDeduplicator

        _log("[ai-pipeline] Starting semantic dedup pass...")
        deduplicator = JobDeduplicator(threshold=0.6)
        clusters = deduplicator.find_duplicates(limit=5000)
        if clusters:
            dedup_archived = deduplicator.merge_duplicates(clusters)
            _log(f"[ai-pipeline] Semantic dedup: {len(clusters)} clusters, {dedup_archived} duplicates archived.")
        else:
            _log("[ai-pipeline] Semantic dedup: no duplicates found.")
    except Exception as e:
        _log(f"[ai-pipeline] Semantic dedup failed (non-fatal): {type(e).__name__}: {e}", "WARN")

    # ── Stage 2: Salary backfill ─────────────────────────────────────────
    try:
        from scripts.ai.salary_estimator import SalaryEstimator

        _log("[ai-pipeline] Starting salary backfill...")
        estimator = SalaryEstimator()
        salary_backfilled = estimator.estimate_all_undisclosed()
        _log(f"[ai-pipeline] Salary backfill: {salary_backfilled} jobs updated.")
    except Exception as e:
        _log(f"[ai-pipeline] Salary backfill failed (non-fatal): {type(e).__name__}: {e}", "WARN")

    duration = round(time.time() - start, 1)
    _log(f"[ai-pipeline] Done in {duration}s — dedup={dedup_archived}, salary={salary_backfilled}")

    return {
        "dedup_archived": dedup_archived,
        "salary_backfilled": salary_backfilled,
        "duration_s": duration,
    }


if __name__ == "__main__":
    import asyncio

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(run_ai_pipeline())
