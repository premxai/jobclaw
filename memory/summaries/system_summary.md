# System Summary

_Updated: 2026-02-20T00:08:00Z_

## Architecture Status

The AI Job Agent is a production-ready autonomous scraping system using **OpenClaw** with **MiniMax M2.5**. It scrapes Google Careers, stores results with dedup, runs on a 10-minute scheduled cycle, and recovers from any crash via checkpoint-based resume.

## Completed Components

- [x] Project structure (`agents/`, `scripts/`, `config/`, `data/`, `logs/`, `state/`, `memory/`)
- [x] Environment setup (`scripts/setup_environment.ps1`)
- [x] Logging utility (`scripts/utils/logger.py`)
- [x] Memory manager (`scripts/utils/memory_manager.py`)
- [x] OpenClaw agent (`agents/google_jobs_agent.yaml`)
- [x] Agent wrapper (`scripts/run_agent.ps1`)
- [x] Storage manager (`scripts/utils/storage_manager.py`)
- [x] Main controller (`scripts/run_scraper.ps1`)
- [x] Cron integration (`scripts/install_cron.ps1`)
- [x] Production safety (retry logic, timeout, error handling, crash recovery)

## Pending Components

_All components implemented._

## Continuation Plan

System is production-ready. To operate:
1. Run `.\scripts\setup_environment.ps1` to verify prerequisites
2. Run `.\scripts\run_scraper.ps1` for a single execution
3. Run `.\scripts\install_cron.ps1` (as Admin) to enable scheduled execution

## Recovery Instructions

1. Check `memory/checkpoints/system_checkpoint.json` for system state
2. Check `memory/sessions/` for latest session log (sorted by timestamp)
3. Run `.\scripts\run_scraper.ps1` — it reads the checkpoint and resumes
4. If `consecutive_failures > 0`, check `logs/system.log` for error details
5. The controller retries 3 times with exponential backoff before marking failure
