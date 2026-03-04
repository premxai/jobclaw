import sqlite3, sys, os
sys.path.insert(0, os.getcwd())

conn = sqlite3.connect('data/jobclaw.db')

# Check job status counts
rows = conn.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status").fetchall()
print("Jobs by status:")
for status, count in rows:
    print(f"  {status}: {count}")

# Check total
total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
print(f"\nTotal jobs: {total}")

# Check bot token validity
from dotenv import load_dotenv
load_dotenv('.env')

bot_token = os.getenv("DISCORD_BOT_TOKEN")
channel_id = os.getenv("DISCORD_CHANNEL_ID")
webhook = os.getenv("DISCORD_WEBHOOK_URL")

print(f"\nBot token set: {'YES' if bot_token else 'NO'}")
print(f"Channel ID set: {'YES — ' + channel_id if channel_id else 'NO'}")
print(f"Webhook URL set: {'YES' if webhook else 'NO (empty)'}")

# Quick test: can we reach Discord API?
if bot_token:
    import urllib.request
    req = urllib.request.Request(
        "https://discord.com/api/v10/users/@me",
        headers={"Authorization": f"Bot {bot_token}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            import json
            data = json.loads(resp.read())
            print(f"Bot identity: {data.get('username')}#{data.get('discriminator')} (ID: {data.get('id')})")
            print("✅ Bot token is VALID")
    except Exception as e:
        print(f"❌ Bot token INVALID or expired: {e}")

conn.close()
