"""
Twitter/X digest pusher — posts a rolling digest of new roles, not a per-job firehose.

Every run (intended cadence: every ~3 hours) it tweets ONE summary like:

    🆕 18 new US tech roles (last 3h)
    💻 7 SWE · 🤖 5 AI/ML · 📊 3 Data · 🎓 3 New Grad
    Top: Senior Backend Engineer @ Stripe; ML Engineer @ OpenAI
    https://norinote.xyz/jobs #techjobs #hiring

One tweet per run (~8/day) stays well under the X free-tier monthly write cap. A
multi-tweet thread is intentionally avoided because it multiplies the tweet count.

Safety: dry-run is the default. It only posts for real when JOBCLAW_TWITTER_DRY_RUN=0
AND all four X API credentials are present. Already-tweeted jobs are tracked in
data/tweeted_hashes.json (separate from Discord's posted_hashes.json) so the two
channels are independent.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

from scripts.database.db_utils import get_connection, is_postgres
from scripts.discord_push import _get_category
from scripts.utils.logger import _log

TWEETED_FILE = PROJECT_ROOT / "data" / "tweeted_hashes.json"
TWEET_MAX_CHARS = 280
URL_WEIGHT = 23  # X counts any link as 23 chars (t.co wrapping)

CATEGORY_EMOJIS = {
    "AI/ML": "🤖",
    "SWE": "💻",
    "Data": "📊",
    "New Grad": "🎓",
    "Product": "📦",
    "Research": "🔬",
    "Design": "🎨",
}


def log(msg: str, level: str = "INFO") -> None:
    _log(msg, level, "twitter_push")


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


def _x_credentials() -> dict | None:
    keys = ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")
    vals = {k: os.getenv(k) for k in keys}
    return vals if all(vals.values()) else None


def _web_url() -> str:
    return os.getenv("JOBCLAW_WEB_URL", "https://norinote.xyz").rstrip("/")


# ─── tweeted-hash dedup (separate from Discord) ────────────────────────
def load_tweeted_hashes() -> dict:
    if TWEETED_FILE.exists():
        try:
            with open(TWEETED_FILE, encoding="utf-8") as f:
                data = json.load(f)
                return data.get("hashes", {}) if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_tweeted_hashes(hashes: dict) -> None:
    # Keep the file bounded — retain the most recent 5,000 entries.
    if len(hashes) > 5000:
        recent = sorted(hashes.items(), key=lambda kv: kv[1], reverse=True)[:5000]
        hashes = dict(recent)
    TWEETED_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TWEETED_FILE, "w", encoding="utf-8") as f:
        json.dump({"_comment": "internal_hashes already tweeted", "hashes": hashes}, f, indent=2)


# ─── job query ─────────────────────────────────────────────────────────
def get_recent_accepted_jobs(window_hours: int) -> list[dict]:
    """Active, accepted jobs first seen within the window, best-quality first."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        placeholder = "%s" if is_postgres() else "?"
        active = "TRUE" if is_postgres() else "1"
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=window_hours)).isoformat()
        cursor.execute(
            f"""
            SELECT internal_hash, title, company, url, first_seen, keywords_matched, quality_score
            FROM jobs
            WHERE is_active = {active}
              AND COALESCE(quality_state, 'needs_review') = 'accepted'
              AND first_seen >= {placeholder}
            ORDER BY quality_score DESC, first_seen DESC
            """,
            (cutoff,),
        )
        cols = [d[0] for d in cursor.description]
        return [dict(r) if hasattr(r, "keys") else dict(zip(cols, r)) for r in cursor.fetchall()]
    finally:
        conn.close()


# ─── digest formatting (pure, unit-tested) ─────────────────────────────
def _tweet_length(text: str, url: str = "") -> int:
    """Approximate X's character count (links always count as 23)."""
    if url and url in text:
        return len(text) - len(url) + URL_WEIGHT
    return len(text)


def _truncate(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def build_digest(jobs: list[dict], web_url: str, window_hours: int = 3, max_top: int = 2) -> str:
    """Build a single ≤280-char digest tweet from the given jobs."""
    link = f"{web_url.rstrip('/')}/jobs"
    n = len(jobs)
    header = f"🆕 {n} new US tech role{'s' if n != 1 else ''} (last {window_hours}h)"

    counts: dict[str, int] = {}
    for j in jobs:
        cat = _get_category(j)
        if cat and cat != "Uncategorized":
            counts[cat] = counts.get(cat, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    parts = [f"{CATEGORY_EMOJIS.get(cat, '•')} {cnt} {cat}" for cat, cnt in ranked[:5]]
    cat_line = " · ".join(parts)

    top = [j for j in jobs if (j.get("title") and j.get("company"))][:max_top]
    top_line = "Top: " + "; ".join(f"{_truncate(j['title'], 38)} @ {_truncate(j['company'], 24)}" for j in top)
    tail = f"{link} #techjobs #hiring"

    # Assemble, dropping optional lines until it fits.
    for candidate in (
        [header, cat_line, top_line, tail],
        [header, cat_line, tail],
        [header, tail],
    ):
        text = "\n".join(line for line in candidate if line.strip())
        if _tweet_length(text, link) <= TWEET_MAX_CHARS:
            return text
    # Last resort: trim the category line hard.
    return "\n".join([header, _truncate(cat_line, 80), tail])


def _post_tweet(text: str, creds: dict) -> bool:
    """Post a tweet via the X API v2. Returns True on success."""
    try:
        import tweepy
    except ImportError:
        log("tweepy not installed — cannot post. Run: pip install tweepy", "ERROR")
        return False
    try:
        client = tweepy.Client(
            consumer_key=creds["X_API_KEY"],
            consumer_secret=creds["X_API_SECRET"],
            access_token=creds["X_ACCESS_TOKEN"],
            access_token_secret=creds["X_ACCESS_SECRET"],
        )
        resp = client.create_tweet(text=text)
        tweet_id = getattr(resp, "data", {}).get("id") if resp else None
        log(f"Tweeted digest (id={tweet_id})")
        return True
    except Exception as e:
        log(f"Tweet failed: {type(e).__name__}: {e}", "ERROR")
        return False


def push_digest_to_twitter() -> int:
    """Build and post (or dry-run) one digest tweet. Returns jobs included."""
    window_hours = int(os.getenv("JOBCLAW_TWITTER_WINDOW_HOURS", "3"))
    dry_run = _env_flag("JOBCLAW_TWITTER_DRY_RUN", True)
    creds = _x_credentials()
    if creds is None and not dry_run:
        log("X API credentials missing — forcing dry-run.", "WARN")
        dry_run = True

    tweeted = load_tweeted_hashes()
    jobs = [j for j in get_recent_accepted_jobs(window_hours) if j["internal_hash"] not in tweeted]
    if not jobs:
        log(f"No new accepted jobs in the last {window_hours}h — nothing to tweet.")
        return 0

    text = build_digest(jobs, _web_url(), window_hours=window_hours)
    log(f"Digest ({len(jobs)} jobs, {_tweet_length(text, _web_url() + '/jobs')} chars):\n{text}")

    if dry_run:
        log("DRY_RUN: not posting. Set JOBCLAW_TWITTER_DRY_RUN=0 and add X_* keys to go live.")
        return len(jobs)

    if not _post_tweet(text, creds):
        return 0

    now = datetime.now(timezone.utc).isoformat()
    for j in jobs:
        tweeted[j["internal_hash"]] = now
    save_tweeted_hashes(tweeted)
    log(f"Marked {len(jobs)} jobs as tweeted.")
    return len(jobs)


if __name__ == "__main__":
    push_digest_to_twitter()
