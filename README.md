# Architecture
Autonomous multi-threaded job scraping system designed to scale 5,000+ top tech companies safely. Uses decoupled, lightweight micro-scrapers coordinated by an OS-level Task Scheduler, pushing data concurrently to an SQLite database (`jobclaw.db`) with WAL mode enabled.

## Micro-Scraper Architecture

```
jobclaw/
├── config/                          
│   └── company_registry.json        # Central ATS targeting source of truth
├── data/
│   └── jobclaw.db                   # SQLite WAL database for high-concurrency 
├── scripts/
│   ├── database/
│   │   ├── init_db.py               # Main DB setup
│   │   └── db_utils.py              # Common injection & deduplication utils
│   ├── ingestion/
│   │   ├── scrape_ats.py            # Micro-scraper: Greenhouse/Lever/Workday
│   │   ├── scrape_rss.py            # Micro-scraper: RemoteOK/Wellfound/Aggregators
│   │   ├── scrape_github.py         # Micro-scraper: Simplify/PittCSC/Markdown Repos
│   │   └── scrape_openclaw.py       # Micro-scraper: LinkedIn/Indeed (Bot Bypass)
│   ├── discord_bot.py               # Headless Broadcaster (runs as daemon)
│   └── install_schedulers.ps1       # Registers all scrapers to OS Scheduler
```

### 1. Data Ingestion Lifecycle
1. Unique scrapers wake up on independent schedules (e.g., ATS every 30 mins, RSS every 60 mins)
2. They do not block each other nor do they conflict
3. Each extracts, normalizes, applies role/time filters
4. Each uses `INSERT OR IGNORE` to atomically add jobs with an `internal_hash` to the SQLite Database.

### 2. Discord Broadcasting Layer
1. `discord_bot.py` is entirely separated from the ingestion loops
2. It polls the database every 15 minutes checking for `status = 'unposted'`
3. Jobs are flushed to Discord gracefully and marked as `posted` instantly

---

## Execution Instructions

### Prerequisites
- **OpenClaw**: `npm i -g @openclaw/cli` (Only needed for scrape_openclaw.py)
- **Python 3.10+**: `pip install -r requirements.txt`

### 1. Configure the Environment
Create a `.env` file in the root directory:
```env
DISCORD_BOT_TOKEN="your_token"
DISCORD_CHANNEL_ID="channel_id"
MINIMAX_API_KEY="your_minimax_key" # Required for OpenClaw Browser Bypass
```

### 2. Initialize Database & Migrate Legacy Data
```powershell
python scripts/database/init_db.py
```

### 3. Start the Background Scrapers (Production)
Run the automated installation script as Administrator to link scripts to Windows Task Scheduler:
```powershell
.\scripts\install_schedulers.ps1
```
*(Or on Linux/MacOS, simply map the `scripts/ingestion/*.py` files to your CronTab)*

### 4. Start the Headless Broadcaster
In a background terminal, run:
```powershell
python scripts/discord_bot.py
```
TODAY -- 2/23/2026
