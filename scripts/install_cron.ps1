<#
.SYNOPSIS
    Install Windows Scheduled Tasks for ZERO-MISS job scraping.
.DESCRIPTION
    Registers 3 scheduled tasks matching the --tier system:
      - JobClaw_Fast    (every 5 min)  — RSS + GitHub + ATS (1 rotating shard, ~2min)
      - JobClaw_Medium  (every 30 min) — + Enterprise APIs (1 rotating shard, ~4min)
      - JobClaw_Deep    (every 6 hr)   — Everything + Stealth, ALL shards (~15min)

    COVERAGE GUARANTEE:
      fast runs every 5 min × 4 shards = full 11,822 companies every 20 min
      deep runs 4× daily as a safety net (no sharding = complete sweep)

    Each task runs run_scraper.ps1 with the appropriate --tier flag.
    Tasks are resumable — if the system reboots, they auto-restart.

    Run as Administrator for best results.
#>

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $ProjectRoot) { $ProjectRoot = (Get-Location).Path }

$LogFile = Join-Path $ProjectRoot "logs\system.log"
$ScraperScript = Join-Path $ProjectRoot "scripts\run_scraper.ps1"

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $entry = "$timestamp | $Level | [install_scheduler] $Message"
    Write-Host $entry
    $logDir = Split-Path $LogFile -Parent
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
    Add-Content -Path $LogFile -Value $entry
}

# ── Tier definitions (ZERO-MISS: every tier includes ATS) ─────────────
$tiers = @(
    @{
        Name    = "JobClaw_Fast"
        Tier    = "fast"
        Minutes = 5
        Timeout = 5
        Desc    = "RSS + GitHub + ATS 1 shard (~2min) — full coverage every 20min"
    },
    @{
        Name    = "JobClaw_Medium"
        Tier    = "medium"
        Minutes = 30
        Timeout = 10
        Desc    = "RSS + GitHub + Enterprise + ATS 1 shard (~4min)"
    },
    @{
        Name    = "JobClaw_Deep"
        Tier    = "deep"
        Minutes = 360
        Timeout = 30
        Desc    = "Full sweep ALL shards + Stealth (~15min) — safety net 4x daily"
    }
)

Write-Log "========== ZERO-MISS SCHEDULER INSTALLATION =========="
Write-Log "Project root: $ProjectRoot"

foreach ($tier in $tiers) {
    $taskName = $tier.Name
    Write-Log "Installing task: $taskName ($($tier.Desc))"

    # Remove existing task if present
    $existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($existing) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Log "  Removed existing task: $taskName"
    }

    # Also clean up old Heavy task if it exists
    $oldHeavy = Get-ScheduledTask -TaskName "JobClaw_Heavy" -ErrorAction SilentlyContinue
    if ($oldHeavy) {
        Unregister-ScheduledTask -TaskName "JobClaw_Heavy" -Confirm:$false
        Write-Log "  Removed legacy task: JobClaw_Heavy"
    }

    # Action: run scraper with tier flag
    $action = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScraperScript`" -Tier $($tier.Tier)" `
        -WorkingDirectory $ProjectRoot

    # Trigger: repeating interval
    $trigger = New-ScheduledTaskTrigger `
        -Once `
        -At (Get-Date) `
        -RepetitionInterval (New-TimeSpan -Minutes $tier.Minutes) `
        -RepetitionDuration (New-TimeSpan -Days 365)

    # Settings
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit (New-TimeSpan -Minutes $tier.Timeout) `
        -MultipleInstances IgnoreNew

    # Principal
    $principal = New-ScheduledTaskPrincipal `
        -UserId $env:USERNAME `
        -LogonType Interactive `
        -RunLevel Limited

    # Register
    Register-ScheduledTask `
        -TaskName $taskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description $tier.Desc `
        -Force

    Write-Log "  OK: $taskName installed (every $($tier.Minutes) min, timeout $($tier.Timeout) min)"
}

Write-Log ""
Write-Log "COVERAGE GUARANTEE:"
Write-Log "  Fast (5min) x 4 shards = full 11,822 companies every 20 minutes"
Write-Log "  Deep (6hr) = complete sweep with no sharding, 4x daily"
Write-Log ""
Write-Log "========== INSTALLATION COMPLETE =========="
Write-Log "Tasks installed: $($tiers.Count)"
Write-Log ""
Write-Log "To check status: Get-ScheduledTask | Where-Object { `$_.TaskName -like 'JobClaw_*' }"
Write-Log "To run now:      Start-ScheduledTask -TaskName 'JobClaw_Fast'"
