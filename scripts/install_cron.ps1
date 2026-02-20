<#
.SYNOPSIS
    Install Windows Scheduled Task for automated job scraping.
.DESCRIPTION
    Registers a scheduled task that runs run_scraper.ps1 every 10 minutes.
    Task is resumable — if the system reboots, the task auto-restarts.
#>

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $ProjectRoot) { $ProjectRoot = (Get-Location).Path }

$LogFile = Join-Path $ProjectRoot "logs\system.log"
$TaskName = "AIJobAgent_Scraper"
$ScraperScript = Join-Path $ProjectRoot "scripts\run_scraper.ps1"

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $entry = "$timestamp | $Level | [install_cron] $Message"
    Write-Host $entry
    $logDir = Split-Path $LogFile -Parent
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
    Add-Content -Path $LogFile -Value $entry
}

Write-Log "========== CRON INSTALLATION START =========="

# ── Check if task already exists ──────────────────────────────────────
$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Write-Log "Task '$TaskName' already exists. Removing old task..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Log "Old task removed."
}

# ── Create scheduled task ─────────────────────────────────────────────
Write-Log "Registering scheduled task: $TaskName"
Write-Log "Script: $ScraperScript"
Write-Log "Interval: 10 minutes"

# Action: run PowerShell with the scraper script
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScraperScript`"" `
    -WorkingDirectory $ProjectRoot

# Trigger: every 10 minutes, starting now
$trigger = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes 10) `
    -RepetitionDuration (New-TimeSpan -Days 365)

# Settings: restart on failure, run even if on battery
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

# Principal: run as current user
$principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive `
    -RunLevel Limited

# Register
try {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description "AI Job Agent — scrapes Google Careers every 10 minutes" `
        -Force

    Write-Log "Scheduled task registered successfully."
    Write-Log "Task name: $TaskName"
    Write-Log "Interval: every 10 minutes"
    Write-Log "Next run: $((Get-ScheduledTask -TaskName $TaskName | Get-ScheduledTaskInfo).NextRunTime)"
} catch {
    Write-Log "Failed to register scheduled task: $_" "ERROR"
    Write-Log "You may need to run this script as Administrator." "ERROR"
    exit 1
}

# ── Verify ────────────────────────────────────────────────────────────
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($task) {
    Write-Log "Verification: Task state = $($task.State)"
    Write-Log "To disable:  Unregister-ScheduledTask -TaskName '$TaskName'"
    Write-Log "To check:    Get-ScheduledTask -TaskName '$TaskName'"
} else {
    Write-Log "Verification FAILED — task not found after registration." "ERROR"
    exit 1
}

Write-Log "========== CRON INSTALLATION COMPLETE =========="
