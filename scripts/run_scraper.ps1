<#
.SYNOPSIS
    JobClaw v4 scraper wrapper for Windows Task Scheduler.
.DESCRIPTION
    Accepts a -Tier parameter (fast|medium|heavy|deep) and
    runs run_all_scrapers.py with the corresponding --tier flag.
    Logs output to logs/system.log.

    Called by the scheduled tasks registered via install_cron.ps1.
#>

param(
    [ValidateSet("fast", "medium", "heavy", "deep")]
    [string]$Tier = "fast"
)

$ErrorActionPreference = "Continue"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $ProjectRoot) { $ProjectRoot = (Get-Location).Path }

$LogFile = Join-Path $ProjectRoot "logs\system.log"

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $entry = "$timestamp | $Level | [run_scraper] $Message"
    Write-Host $entry
    $logDir = Split-Path $LogFile -Parent
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
    Add-Content -Path $LogFile -Value $entry
}

Write-Log "===== SCRAPER RUN START (tier=$Tier) ====="

$startTime = Get-Date
$scraperScript = Join-Path $ProjectRoot "scripts\ingestion\run_all_scrapers.py"

try {
    $output = & python $scraperScript --tier $Tier 2>&1
    $exitCode = $LASTEXITCODE

    # Log Python output
    $output | ForEach-Object { Write-Log "  $_" }

    if ($exitCode -eq 0 -or $null -eq $exitCode) {
        Write-Log "Scraper completed successfully."
    }
    else {
        Write-Log "Scraper exited with code $exitCode" "WARN"
    }
}
catch {
    Write-Log "Scraper failed: $_" "ERROR"
}

$elapsed = (Get-Date) - $startTime
Write-Log "===== SCRAPER RUN COMPLETE (tier=$Tier, ${elapsed}s) ====="
