"""
Scraper Health Tracker — monitors scraper performance and generates alerts.

Tracks per-run metrics:
- Duration
- Companies scraped/skipped
- Jobs found/new
- Errors by type
- Retry queue size

Generates alerts when:
- Error rate > 5% (warning) or > 15% (critical)
- Retry queue > 100 (warning)
- No new jobs in 6+ hours (warning)
"""

import json
import time
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent


class HealthTracker:
    """
    Tracks scraper health metrics and generates alerts.
    """

    def __init__(self, path: Path = None):
        self.path = path or PROJECT_ROOT / "state" / "scraper_health.json"
        self._data = self._load()
        self._start_time = None
        self._errors = {}

    def _load(self) -> dict:
        """Load health data from disk."""
        if self.path.exists():
            try:
                with open(self.path, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, KeyError):
                pass
        return self._empty_state()

    def _empty_state(self) -> dict:
        return {
            "last_run": None,
            "duration_seconds": 0,
            "companies_scraped": 0,
            "companies_skipped": 0,
            "jobs_found": 0,
            "new_jobs": 0,
            "errors": {},
            "retry_queue_size": 0,
        }

    def save(self) -> None:
        """Persist health data to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(
                {"_comment": "Scraper health metrics for monitoring", "_schema_version": 1, **self._data}, f, indent=2
            )

    def start_run(self) -> None:
        """Mark the start of a scraper run."""
        self._start_time = time.time()
        self._errors = {}

    def end_run(
        self,
        companies_scraped: int,
        companies_skipped: int,
        jobs_found: int,
        new_jobs: int,
        errors: dict,
        retry_queue_size: int,
    ) -> None:
        """Record metrics at the end of a run."""
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        duration = time.time() - self._start_time if self._start_time else 0

        self._data = {
            "last_run": now,
            "duration_seconds": round(duration, 1),
            "companies_scraped": companies_scraped,
            "companies_skipped": companies_skipped,
            "jobs_found": jobs_found,
            "new_jobs": new_jobs,
            "errors": errors,
            "retry_queue_size": retry_queue_size,
        }
        self.save()

    def record_error(self, error_type: str) -> None:
        """Record an error during the run."""
        self._errors[error_type] = self._errors.get(error_type, 0) + 1

    def get_alerts(self) -> list[dict]:
        """
        Generate alerts based on current health state.

        Returns list of {"level": "warning|critical", "message": str}
        """
        alerts = []

        # Calculate error rate
        total = self._data.get("companies_scraped", 0) + self._data.get("companies_skipped", 0)
        total_errors = sum(self._data.get("errors", {}).values())

        if total > 0:
            error_rate = total_errors / total
            if error_rate > 0.15:
                alerts.append(
                    {"level": "critical", "message": f"High error rate: {error_rate:.1%} ({total_errors} errors)"}
                )
            elif error_rate > 0.05:
                alerts.append(
                    {"level": "warning", "message": f"Elevated error rate: {error_rate:.1%} ({total_errors} errors)"}
                )

        # Check retry queue size
        retry_size = self._data.get("retry_queue_size", 0)
        if retry_size > 100:
            alerts.append({"level": "warning", "message": f"Large retry queue: {retry_size} companies pending"})

        # Check for stale data (no new jobs in 6+ hours)
        last_run = self._data.get("last_run")
        if last_run:
            try:
                last_dt = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
                hours_since = (datetime.now(UTC) - last_dt).total_seconds() / 3600

                if hours_since > 6 and self._data.get("new_jobs", 0) == 0:
                    alerts.append(
                        {"level": "warning", "message": f"No new jobs found in last {int(hours_since)} hours"}
                    )
            except (ValueError, TypeError):
                pass

        return alerts

    def get_summary(self) -> str:
        """Get human-readable health summary."""
        lines = [
            f"Last run: {self._data.get('last_run', 'never')}",
            f"Duration: {self._data.get('duration_seconds', 0)}s",
            f"Companies: {self._data.get('companies_scraped', 0)} scraped, "
            f"{self._data.get('companies_skipped', 0)} skipped",
            f"Jobs: {self._data.get('jobs_found', 0)} found, {self._data.get('new_jobs', 0)} new",
            f"Retry queue: {self._data.get('retry_queue_size', 0)}",
        ]

        errors = self._data.get("errors", {})
        if errors:
            error_str = ", ".join(f"{k}={v}" for k, v in errors.items())
            lines.append(f"Errors: {error_str}")

        return "\n".join(lines)


def format_discord_alert(alerts: list[dict]) -> str | None:
    """
    Format alerts for Discord notification.

    Returns None if no alerts, otherwise formatted message.
    """
    if not alerts:
        return None

    critical = [a for a in alerts if a["level"] == "critical"]
    warnings = [a for a in alerts if a["level"] == "warning"]

    lines = ["**⚠️ JobClaw Health Alert**\n"]

    if critical:
        lines.append("🔴 **Critical:**")
        for a in critical:
            lines.append(f"  • {a['message']}")

    if warnings:
        lines.append("🟡 **Warning:**")
        for a in warnings:
            lines.append(f"  • {a['message']}")

    return "\n".join(lines)
