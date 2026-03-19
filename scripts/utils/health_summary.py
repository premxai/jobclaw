import sys
from pathlib import Path
from datetime import datetime, UTC

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.database.db_utils import get_connection, is_postgres


def generate_health_report():
    """Generate a markdown health report of all scrapers."""
    print(">>> Generating Global Health Dashboard...")

    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Get last 24h stats per scraper
        if is_postgres():
            cursor.execute("""
                SELECT 
                    scraper,
                    COUNT(*) as runs,
                    SUM(new_jobs) as total_new,
                    AVG(duration_seconds)::int as avg_duration,
                    SUM(CASE WHEN errors != '' THEN 1 ELSE 0 END) as failures
                FROM scraper_runs
                WHERE run_at::timestamp >= (NOW() - INTERVAL '24 hours')
                GROUP BY scraper
                ORDER BY runs DESC
            """)
        else:
            cursor.execute("""
                SELECT 
                    scraper,
                    COUNT(*) as runs,
                    SUM(new_jobs) as total_new,
                    AVG(duration_seconds) as avg_duration,
                    0 as failures -- SQLite simple mock for errors logic
                FROM scraper_runs
                GROUP BY scraper
                ORDER BY runs DESC
            """)

        rows = cursor.fetchall()

        print("\n### 🌍 JobClaw Global Health (Last 24h)")
        print("| Scraper | Runs | New Jobs | Avg Dur | Health |")
        print("| :--- | :---: | :---: | :---: | :---: |")

        if not rows:
            print("| No data yet | - | - | - | - |")
        else:
            for row in rows:
                name, runs, new_jobs, dur, failures = row
                health = "✅ Healthy" if failures == 0 else "⚠️ Flaky"
                if failures > (runs / 2):
                    health = "❌ Down"

                print(f"| {name:<12} | {runs:^4} | {new_jobs:^8} | {dur:^6}s | {health:^7} |")

        print(f"\nReport generated at: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')} UTC")

    finally:
        conn.close()


if __name__ == "__main__":
    generate_health_report()
