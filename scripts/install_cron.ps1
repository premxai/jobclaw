<#
.SYNOPSIS
    Install Windows Scheduled Tasks for tiered job scraping automation.
.DESCRIPTION
    Registers 4 scheduled tasks matching the --tier system:
      - JobClaw_Fast    (every 5 min)  — RSS + GitHub only (~30s)
      - JobClaw_Medium  (every 30 min) — + Enterprise APIs (~3min)
      - JobClaw_Heavy   (every 1 hr)   — + ATS boards sharded (~4min)
      - JobClaw_Deep    (every 4 hr)   — Everything incl. OpenClaw (~15min)

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

# ── Tier definitions ─────────────────────────────────────────────────
$tiers = @(
    @{
        Name    = "JobClaw_Fast"
        Tier    = "fast"
        Minutes = 5
        Timeout = 2
        Desc    = "RSS + GitHub only (~30s)"
    },
    @{
        Name    = "JobClaw_Medium"
        Tier    = "medium"
        Minutes = 30
        Timeout = 10
        Desc    = "RSS + GitHub + Enterprise APIs (~3min)"
    },
    @{
        Name    = "JobClaw_Heavy"
        Tier    = "heavy"
        Minutes = 60
        Timeout = 15
        Desc    = "RSS + GitHub + Enterprise + ATS sharded (~4min)"
    },
    @{
        Name    = "JobClaw_Deep"
        Tier    = "deep"
        Minutes = 240
        Timeout = 30
        Desc    = "Full sweep including OpenClaw (~15min)"
    }
)

Write-Log "========== TIERED SCHEDULER INSTALLATION =========="
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
        -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
        -LogonType Interactive `
        -RunLevel Limited

    try {
        Register-ScheduledTask `
            -TaskName $taskName `
            -Action $action `
            -Trigger $trigger `
            -Settings $settings `
            -Principal $principal `
            -Description "JobClaw v4 — $($tier.Desc) — every $($tier.Minutes)min" `
            -Force | Out-Null

        Write-Log "  ✅ Registered: $taskName (every $($tier.Minutes)min, timeout $($tier.Timeout)min)"
    }
    catch {
        Write-Log "  ❌ Failed to register $taskName : $_" "ERROR"
    }
}

# ── Summary ──────────────────────────────────────────────────────────
Write-Log ""
Write-Log "=== SCHEDULED TASKS SUMMARY ==="
foreach ($tier in $tiers) {
    $task = Get-ScheduledTask -TaskName $tier.Name -ErrorAction SilentlyContinue
    if ($task) {
        $info = $task | Get-ScheduledTaskInfo
        Write-Log "  $($tier.Name): State=$($task.State), Next=$($info.NextRunTime)"
    }
    else {
        Write-Log "  $($tier.Name): NOT FOUND" "WARN"
    }
}

Write-Log ""
Write-Log "To disable all: .\scripts\uninstall_scheduler.ps1"
Write-Log "To check status: Get-ScheduledTask | Where-Object { `$_.TaskName -like 'JobClaw_*' }"
Write-Log "========== INSTALLATION COMPLETE =========="
