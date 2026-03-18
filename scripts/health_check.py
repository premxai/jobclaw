"""Health check — verifies database connectivity and module imports."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.database.db_utils import get_connection, is_postgres


def check_database():
    """Print database stats."""
    try:
        conn = get_connection()
        backend = "PostgreSQL" if is_postgres() else "SQLite"
        total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        active = conn.execute("SELECT COUNT(*) FROM jobs WHERE is_active=1").fetchone()[0]
        sources = conn.execute(
            "SELECT source_ats, COUNT(*) c FROM jobs GROUP BY source_ats ORDER BY c DESC LIMIT 15"
        ).fetchall()

        # Recent jobs — syntax differs per backend
        if is_postgres():
            recent_q = "SELECT COUNT(*) FROM jobs WHERE first_seen >= NOW() - INTERVAL '24 hours'"
        else:
            recent_q = "SELECT COUNT(*) FROM jobs WHERE first_seen >= datetime('now','-24 hours')"
        recent = conn.execute(recent_q).fetchone()[0]
        conn.close()

        print(f"Backend: {backend}")
        print(f"Total jobs: {total}")
        print(f"Active jobs: {active}")
        print(f"Added last 24h: {recent}")
        print("By source:")
        for s, c in sources:
            print(f"  {s or 'unknown'}: {c}")
    except Exception as e:
        print(f"ERROR: Database check failed — {e}")


def check_imports():
    """Verify all critical modules can be imported."""
    print()
    print("Module import checks:")
    checks = [
        ("RSS", "scripts.ingestion.scrape_rss", "run_rss_scraper"),
        ("GitHub", "scripts.ingestion.scrape_github", "run_github_scraper"),
        ("ATS", "scripts.ingestion.scrape_ats", "run_ats_scraper"),
        ("Enterprise", "scripts.ingestion.scrape_enterprise", None),
        ("Discord", "scripts.discord_push", "push_new_jobs_to_discord"),
        ("DB Utils", "scripts.database.db_utils", "get_connection"),
        ("Role Filter", "scripts.ingestion.role_filter", "passes_role_filter"),
    ]
    for name, mod, fn in checks:
        try:
            m = __import__(mod, fromlist=[fn] if fn else [""])
            if fn and not hasattr(m, fn):
                print(f"  [{name}] IMPORT OK — missing function: {fn}")
            else:
                print(f"  [{name}] OK")
        except Exception as e:
            print(f"  [{name}] IMPORT ERROR — {e}")


if __name__ == "__main__":
    check_database()
    check_imports()
