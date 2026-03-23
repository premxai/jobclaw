import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
from scripts.database.db_utils import get_connection

conn = get_connection()
cursor = conn.cursor()

migrations = [
    "ALTER TABLE scraper_runs ADD COLUMN IF NOT EXISTS shard_index INTEGER DEFAULT 0;",
    "ALTER TABLE companies ADD COLUMN IF NOT EXISTS tier TEXT DEFAULT 'P1';",
]

for m in migrations:
    try:
        cursor.execute(m)
        conn.commit()
        print("Success:", m)
    except Exception as e:
        conn.rollback()
        print("Skipped/Failed:", m, "->", e)

print("Migration completed.")
