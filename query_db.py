import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
from scripts.database.db_utils import get_connection

conn = get_connection()
cursor = conn.cursor()

try:
    cursor.execute("SELECT COUNT(*) FROM jobs")
    print("Total jobs in DB:", cursor.fetchone()[0])

    cursor.execute("SELECT COUNT(*) FROM jobs WHERE status = 'unposted'")
    unposted = cursor.fetchone()[0]
    print("Unposted jobs:", unposted)

    cursor.execute("SELECT COUNT(*) FROM jobs WHERE status = 'unposted' AND quality_score >= 30")
    print("Unposted Jobs >= 30 score:", cursor.fetchone()[0])

    cursor.execute("SELECT quality_score, COUNT(*) FROM jobs GROUP BY quality_score ORDER BY quality_score DESC")
    print("Quality Score Distribution:", cursor.fetchall()[:10])
except Exception as e:
    print("DB Error:", e)
