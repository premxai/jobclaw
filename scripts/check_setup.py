"""
Pre-flight setup validator for JobClaw.

Checks database connectivity, Discord credentials, config files, and shard state.
Run before first deployment or when debugging a silent pipeline.

Usage:
    python scripts/check_setup.py

Exit code 0 = all checks passed. Exit code 1 = one or more checks failed.
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

PASS = "✓ PASS"
FAIL = "✗ FAIL"
WARN = "⚠ WARN"

failures = []


def check(label: str, ok: bool, detail: str = "", warn_only: bool = False) -> None:
    status = PASS if ok else (WARN if warn_only else FAIL)
    line = f"  {status}  {label}"
    if detail:
        line += f"  ({detail})"
    print(line)
    if not ok and not warn_only:
        failures.append(label)


# ── 1. Database ────────────────────────────────────────────────────────────────
print("\n[1] Database")
try:
    from scripts.database.db_utils import get_connection, is_postgres, DB_PATH

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1")

    if is_postgres():
        import re
        db_url = os.environ.get("DATABASE_URL", "")
        host_match = re.search(r"@([^:/]+)", db_url)
        host = host_match.group(1) if host_match else "unknown"
        backend_info = f"PostgreSQL host={host}"
    else:
        backend_info = f"SQLite at {DB_PATH}"

    check("DB connectivity", True, backend_info)

    cur.execute("SELECT COUNT(*) FROM jobs")
    total = cur.fetchone()[0]
    check("jobs table accessible", True, f"{total} total jobs")

    cur.execute("SELECT COUNT(*) FROM jobs WHERE status='unposted'")
    unposted = cur.fetchone()[0]
    check(
        "unposted jobs exist",
        unposted > 0,
        f"{unposted} unposted",
        warn_only=True,  # ok to be 0 on first run
    )

    if not is_postgres():
        check(
            "using PostgreSQL (required for GitHub Actions)",
            False,
            "SQLite is ephemeral on CI — set DATABASE_URL to a persistent PostgreSQL instance",
        )

    conn.close()
except Exception as e:
    check("DB connectivity", False, str(e))

# ── 2. Discord credentials ─────────────────────────────────────────────────────
print("\n[2] Discord Credentials")
webhook = os.environ.get("DISCORD_WEBHOOK_URL", "")
bot_token = os.environ.get("DISCORD_BOT_TOKEN", "")
general_channel = os.environ.get("DISCORD_CHANNEL_ID", "")

has_webhook = bool(webhook)
has_bot = bool(bot_token) and bool(general_channel)
check(
    "Discord transport configured (WEBHOOK or BOT+CHANNEL)",
    has_webhook or has_bot,
    "DISCORD_WEBHOOK_URL" if has_webhook else ("BOT+CHANNEL_ID" if has_bot else "none set"),
)

CATEGORY_CHANNELS = {
    "DISCORD_CHANNEL_AI": os.environ.get("DISCORD_CHANNEL_AI", ""),
    "DISCORD_CHANNEL_SWE": os.environ.get("DISCORD_CHANNEL_SWE", ""),
    "DISCORD_CHANNEL_DATA": os.environ.get("DISCORD_CHANNEL_DATA", ""),
    "DISCORD_CHANNEL_NEWGRAD": os.environ.get("DISCORD_CHANNEL_NEWGRAD", ""),
    "DISCORD_CHANNEL_PRODUCT": os.environ.get("DISCORD_CHANNEL_PRODUCT", ""),
    "DISCORD_CHANNEL_RESEARCH": os.environ.get("DISCORD_CHANNEL_RESEARCH", ""),
}
missing_channels = [k for k, v in CATEGORY_CHANNELS.items() if not v]
if missing_channels:
    check(
        "category channels configured",
        False,
        f"missing: {', '.join(missing_channels)} — jobs will fall back to DISCORD_CHANNEL_ID",
        warn_only=True,
    )
else:
    check("category channels configured", True, "all 6 set")

# ── 3. Config files ────────────────────────────────────────────────────────────
print("\n[3] Config Files")
import json

registry = PROJECT_ROOT / "config" / "company_registry.json"
try:
    data = json.loads(registry.read_text())
    count = len(data) if isinstance(data, list) else len(data.get("companies", data))
    check("company_registry.json", count > 0, f"{count} companies")
except Exception as e:
    check("company_registry.json", False, str(e))

hot = PROJECT_ROOT / "config" / "hot_companies.json"
try:
    data = json.loads(hot.read_text())
    companies = data.get("companies", data) if isinstance(data, dict) else data
    check("hot_companies.json", len(companies) > 0, f"{len(companies)} hot companies")
except Exception as e:
    check("hot_companies.json", False, str(e))

dedup = PROJECT_ROOT / "data" / "posted_hashes.json"
if dedup.exists():
    try:
        hashes = json.loads(dedup.read_text())
        check("posted_hashes.json", True, f"{len(hashes)} hashes (7-day rolling window)")
    except Exception as e:
        check("posted_hashes.json", False, f"parse error: {e}")
else:
    check("posted_hashes.json", True, "not yet created — will be generated on first push", warn_only=False)

# ── 4. Shard rotation state ────────────────────────────────────────────────────
print("\n[4] Shard Rotation")
try:
    from scripts.database.db_utils import get_connection, is_postgres

    conn = get_connection()
    cur = conn.cursor()
    placeholder = "%s" if is_postgres() else "?"
    cur.execute(
        f"SELECT COUNT(*) FROM scraper_runs WHERE scraper {placeholder if False else 'IS NOT NULL'}".replace(
            "IS NOT NULL", "IS NOT NULL"
        )
    )
    # Simpler: just count all scraper_runs rows
    cur.execute("SELECT COUNT(*) FROM scraper_runs")
    run_count = cur.fetchone()[0]
    next_shard = run_count % 4
    check("scraper_runs table accessible", True, f"{run_count} total runs, next shard = {next_shard}")
    conn.close()
except Exception as e:
    check("scraper_runs table", False, str(e), warn_only=True)

# ── Summary ────────────────────────────────────────────────────────────────────
print()
if not failures:
    print("  ALL CHECKS PASSED\n")
    sys.exit(0)
else:
    print(f"  {len(failures)} CHECK(S) FAILED:")
    for f in failures:
        print(f"    - {f}")
    print()
    sys.exit(1)
