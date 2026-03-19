import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def fix():
    from scripts.database.db_utils import get_connection, get_hot_slugs

    conn = get_connection()
    cur = conn.cursor()
    slugs = list(get_hot_slugs())
    if not slugs:
        print("No hot slugs found!")
        return
    placeholders = ",".join(["%s"] * len(slugs))
    cur.execute(f"UPDATE companies SET tier='P0' WHERE slug IN ({placeholders})", slugs)
    conn.commit()
    print(f"Updated {cur.rowcount} companies to P0")
    conn.close()


if __name__ == "__main__":
    fix()
