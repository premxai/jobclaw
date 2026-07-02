"""Platform budget helpers for adaptive ATS queue runs."""

import os
from collections import defaultdict

PLATFORM_WORKERS = {
    "greenhouse": 4,
    "lever": 4,
    "ashby": 4,
    "smartrecruiters": 2,
    # Workday rate-limits per tenant (each company is its own host/WAF), so 8
    # workers touching 8 *different* tenants keeps per-company politeness
    # unchanged while multiplying platform throughput.
    "workday": 8,
    "workable": 1,
    "rippling": 1,
    "bamboohr": 1,
    "gem": 3,
}
DEFAULT_WORKERS = 3

PLATFORM_ESTIMATED_SECONDS = {
    "greenhouse": 4,
    "lever": 4,
    "ashby": 5,
    "gem": 6,
    "smartrecruiters": 8,
    "bamboohr": 8,
    "rippling": 15,
    "workable": 20,
    # Most tenants need one CXS request; 8s covers pagination on bigger boards.
    # (Was 45s from the shared-bucket era, which capped claims at 13/run.)
    "workday": 8,
}
PLATFORM_DEFAULT_BUDGET_SECONDS = {
    "greenhouse": 240,
    "lever": 240,
    "ashby": 240,
    "gem": 180,
    "smartrecruiters": 180,
    "bamboohr": 180,
    "rippling": 240,
    "workable": 240,
    # 780s x 8 workers / 8s = ~780 targets/run, under the 900s ATS task timeout.
    "workday": 780,
}


def platform_budget_seconds(platform: str) -> int:
    key = f"JOBCLAW_PLATFORM_BUDGET_SECONDS_{platform.upper()}"
    return int(os.getenv(key, str(PLATFORM_DEFAULT_BUDGET_SECONDS.get(platform, 180))))


def platform_target_cap(platform: str) -> int:
    """Return the number of targets a platform budget can attempt."""
    platform = str(platform or "").lower()
    workers = max(1, PLATFORM_WORKERS.get(platform, DEFAULT_WORKERS))
    estimate = max(1, PLATFORM_ESTIMATED_SECONDS.get(platform, 10))
    budget = platform_budget_seconds(platform)
    return max(1, int((budget * workers) / estimate))


def apply_platform_budgets(registry: list[dict]) -> tuple[list[dict], list[dict], dict]:
    """Cap target counts by platform time/request budgets."""
    by_platform = defaultdict(list)
    for target in registry:
        by_platform[str(target.get("ats") or "").lower()].append(target)

    selected = []
    dropped = []
    budget_metrics = {}
    for platform, targets in sorted(by_platform.items()):
        budget = platform_budget_seconds(platform)
        estimate = max(1, PLATFORM_ESTIMATED_SECONDS.get(platform, 10))
        workers = max(1, PLATFORM_WORKERS.get(platform, DEFAULT_WORKERS))
        cap = platform_target_cap(platform)
        keep = targets[:cap]
        selected.extend(keep)
        dropped.extend(targets[cap:])
        budget_metrics[platform] = {
            "budget_seconds": budget,
            "estimated_seconds_per_target": estimate,
            "workers": workers,
            "cap": cap,
            "selected": len(keep),
            "dropped": max(0, len(targets) - len(keep)),
        }
    return selected, dropped, budget_metrics
