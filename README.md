# AI Job Agent

Autonomous job scraping system powered by **OpenClaw** and **MiniMax M2.5**. Scrapes Google Careers listings, detects new postings, and runs on a scheduled 10-minute cycle with full crash recovery.

---

## System Purpose

This system automates job discovery from Google Careers by:

1. **Scraping** — An OpenClaw agent navigates Google's careers page and extracts structured job data
2. **Storage** — Results are stored in `data/google_jobs.json` with duplicate detection and change tracking
3. **Scheduling** — A Windows Scheduled Task runs the scraper every 10 minutes
4. **Memory** — Every execution is logged; the system resumes from the last checkpoint after any crash

---

## Architecture Overview

```
ai-job-agent/
├── agents/
│   └── google_jobs_agent.yaml       # OpenClaw agent (MiniMax M2.5)
├── scripts/
│   ├── setup_environment.ps1        # Environment verification
│   ├── run_agent.ps1                # Agent execution wrapper
│   ├── run_scraper.ps1              # Main controller (crash-safe)
│   ├── install_cron.ps1             # Windows Scheduled Task
│   └── utils/
│       ├── logger.py                # Dual logging (file + stdout)
│       ├── memory_manager.py        # Session/checkpoint/summary I/O
│       └── storage_manager.py       # Job storage + dedup + change detect
├── config/                          # Configuration files
├── data/
│   └── google_jobs.json             # Persisted job listings
├── logs/
│   └── system.log                   # Runtime logs
├── state/                           # Runtime state
└── memory/
    ├── sessions/                    # session_<timestamp>.md per run
    ├── checkpoints/
    │   └── system_checkpoint.json   # Current state + next task
    └── summaries/
        └── system_summary.md        # Architecture + recovery
```

### Execution Flow

```
run_scraper.ps1
  ├── Read checkpoint → determine resume point
  ├── Initialize memory directories
  ├── Execute OpenClaw agent (with retry × 3, exponential backoff)
  ├── Store results via storage_manager.py (dedup + change detect)
  ├── Update checkpoint (read-before-write)
  ├── Write session log to memory/sessions/
  └── Exit (cron re-triggers in 10 min)
```

### Production Safety Features

| Feature | Implementation |
|---|---|
| **Retry logic** | 3 attempts with exponential backoff (5s → 10s → 20s, capped 60s) |
| **Timeout** | Agent execution capped at 120 seconds |
| **Crash recovery** | Checkpoint persists state; controller resumes from last valid state |
| **Atomic writes** | All file writes go to `.tmp` first, then rename |
| **Read-before-write** | Checkpoint is always loaded before updates |
| **Error tracking** | `consecutive_failures` counter in checkpoint |
| **Scheduled restart** | Windows task auto-restarts on failure (3 retries, 1-min interval) |

---

## Memory Architecture

### Memory Files

| File | Purpose | Updated |
|---|---|---|
| `system_checkpoint.json` | System state, last session, next task, error count | Every run |
| `system_summary.md` | Architecture overview, component status | Every session |
| `session_<ts>.md` | What was attempted, results, next steps | Every run |

### How Agents Resume from Memory Files

1. `run_scraper.ps1` reads `system_checkpoint.json` on startup
2. `status` field indicates system health (`production_ready`, `error_recovery`)
3. `next_session` tells the controller what to do
4. If the last run crashed mid-execution, checkpoint retains pre-crash state → same step retries
5. `consecutive_failures` tracks how often the same step has failed
6. Session logs provide detailed audit trail for debugging
7. `system_summary.md` gives full context to any agent (human or AI) picking up the work

### Recovery Protocol

```powershell
# 1. Check system state
Get-Content memory\checkpoints\system_checkpoint.json | ConvertFrom-Json

# 2. Check last session
Get-ChildItem memory\sessions\ | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | Get-Content

# 3. Check error log
Get-Content logs\system.log | Select-Object -Last 50

# 4. Resume
.\scripts\run_scraper.ps1
```

---

## Execution Instructions

### Prerequisites

- **OpenClaw**: `npm install -g openclaw@latest`
- **Python 3.10+**: Required for utility scripts
- **MiniMax API key**: Get from [platform.minimax.io](https://platform.minimax.io)

### Setup

```powershell
# 1. Clone the repo
git clone https://github.com/premxai/jobclaw.git
cd job_agent

# 2. Set API key
$env:MINIMAX_API_KEY = "your-key-here"
# Or create .env file with: MINIMAX_API_KEY=your-key-here

# 3. Verify environment
.\scripts\setup_environment.ps1
```

### Run Once

```powershell
.\scripts\run_scraper.ps1
```

### Run on Schedule (every 10 minutes)

```powershell
# Requires Administrator privileges
.\scripts\install_cron.ps1

# Check scheduled task status
Get-ScheduledTask -TaskName "AIJobAgent_Scraper"

# Remove scheduled task
Unregister-ScheduledTask -TaskName "AIJobAgent_Scraper"
```

### Recovery After Crash

```powershell
# The controller auto-recovers via checkpoint. Just re-run:
.\scripts\run_scraper.ps1
```
