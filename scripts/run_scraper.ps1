<#
.SYNOPSIS
    Main controller for AI Job Agent scraper.
.DESCRIPTION
    Reads checkpoint, initializes memory, executes agent, stores results,
    updates checkpoint, writes session log. Supports crash recovery,
    safe restart, and continuation from checkpoint.
#>

param(
    [switch]$Force  # Force run even if checkpoint says production_ready
)

$ErrorActionPreference = "Continue"  # Don't hard-stop on non-critical errors
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $ProjectRoot) { $ProjectRoot = (Get-Location).Path }

$LogFile = Join-Path $ProjectRoot "logs\system.log"
$CheckpointFile = Join-Path $ProjectRoot "memory\checkpoints\system_checkpoint.json"
$PythonScript = Join-Path $ProjectRoot "scripts\utils"

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $entry = "$timestamp | $Level | [run_scraper] $Message"
    Write-Host $entry
    $logDir = Split-Path $LogFile -Parent
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
    Add-Content -Path $LogFile -Value $entry
}

# ═══════════════════════════════════════════════════════════════════════
# 1. READ CHECKPOINT — determine resume point
# ═══════════════════════════════════════════════════════════════════════
Write-Log "========== SCRAPER SESSION START =========="
Write-Log "Reading checkpoint..."

$checkpoint = @{ status = "unknown"; next_session = "setup_environment" }
if (Test-Path $CheckpointFile) {
    try {
        $checkpoint = Get-Content $CheckpointFile -Raw | ConvertFrom-Json
        Write-Log "Checkpoint loaded — status: $($checkpoint.status), next: $($checkpoint.next_session)"
    } catch {
        Write-Log "Failed to read checkpoint, starting fresh: $_" "WARN"
    }
} else {
    Write-Log "No checkpoint found — first run."
}

# ═══════════════════════════════════════════════════════════════════════
# 2. INITIALIZE MEMORY SYSTEM
# ═══════════════════════════════════════════════════════════════════════
Write-Log "Initializing memory system..."
$memoryDirs = @(
    "memory\sessions",
    "memory\checkpoints",
    "memory\summaries"
)
foreach ($dir in $memoryDirs) {
    $fullPath = Join-Path $ProjectRoot $dir
    if (-not (Test-Path $fullPath)) {
        New-Item -ItemType Directory -Path $fullPath -Force | Out-Null
        Write-Log "Created: $dir"
    }
}

# ═══════════════════════════════════════════════════════════════════════
# 3. EXECUTE AGENT
# ═══════════════════════════════════════════════════════════════════════
Write-Log "Executing Google Jobs agent..."
$agentScript = Join-Path $ProjectRoot "scripts\run_agent.ps1"
$agentStartTime = Get-Date
$agentSuccess = $false
$agentError = ""
$retryCount = 0
$maxRetries = 3
$retryDelaySec = 5

while ($retryCount -lt $maxRetries -and -not $agentSuccess) {
    if ($retryCount -gt 0) {
        Write-Log "Retry attempt $retryCount of $maxRetries (waiting ${retryDelaySec}s)..." "WARN"
        Start-Sleep -Seconds $retryDelaySec
        $retryDelaySec = [math]::Min($retryDelaySec * 2, 60)  # exponential backoff, cap 60s
    }

    try {
        & $agentScript
        if ($LASTEXITCODE -eq 0 -or $null -eq $LASTEXITCODE) {
            $agentSuccess = $true
            Write-Log "Agent execution successful."
        } else {
            $agentError = "Agent exited with code $LASTEXITCODE"
            Write-Log $agentError "WARN"
        }
    } catch {
        $agentError = $_.Exception.Message
        Write-Log "Agent error: $agentError" "WARN"
    }

    $retryCount++
}

$agentElapsed = (Get-Date) - $agentStartTime

if (-not $agentSuccess) {
    Write-Log "Agent failed after $maxRetries attempts: $agentError" "ERROR"
}

# ═══════════════════════════════════════════════════════════════════════
# 4. STORE RESULTS
# ═══════════════════════════════════════════════════════════════════════
$storageResult = "no_data"
if ($agentSuccess) {
    Write-Log "Storing results..."
    try {
        $storeOutput = & python (Join-Path $PythonScript "storage_manager.py") 2>&1
        Write-Log "Storage complete."
        $storageResult = "stored"
    } catch {
        Write-Log "Storage failed: $_" "ERROR"
        $storageResult = "storage_error"
    }
}

# ═══════════════════════════════════════════════════════════════════════
# 5. UPDATE CHECKPOINT
# ═══════════════════════════════════════════════════════════════════════
Write-Log "Updating checkpoint..."
$timestamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")

# Read existing checkpoint first (requirement #7)
$existingCheckpoint = @{}
if (Test-Path $CheckpointFile) {
    try {
        $existingCheckpoint = Get-Content $CheckpointFile -Raw | ConvertFrom-Json -AsHashtable
    } catch { }
}

$newCheckpoint = @{
    status              = if ($agentSuccess) { "production_ready" } else { "error_recovery" }
    next_session        = if ($agentSuccess) { "scheduled_run" } else { "retry_agent" }
    last_updated        = $timestamp
    last_completed_session = if ($agentSuccess) { $timestamp } else { $existingCheckpoint["last_completed_session"] }
    system_operational  = $agentSuccess
    last_run_duration_s = [math]::Round($agentElapsed.TotalSeconds, 1)
    last_error          = if ($agentSuccess) { $null } else { $agentError }
    consecutive_failures = if ($agentSuccess) { 0 } else { ([int]$existingCheckpoint["consecutive_failures"] + 1) }
}

$newCheckpoint | ConvertTo-Json -Depth 10 | Set-Content $CheckpointFile -Encoding utf8
Write-Log "Checkpoint updated — status: $($newCheckpoint.status)"

# ═══════════════════════════════════════════════════════════════════════
# 6. WRITE SESSION LOG
# ═══════════════════════════════════════════════════════════════════════
Write-Log "Writing session log..."
$sessionTimestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$sessionFile = Join-Path $ProjectRoot "memory\sessions\session_$sessionTimestamp.md"

$sessionContent = @"
# Session Log — $sessionTimestamp

## What Was Attempted

Scraper controller execution — fetch Google job listings via OpenClaw agent.

## What Was Implemented

- Agent execution: $(if ($agentSuccess) {'SUCCESS'} else {"FAILED after $retryCount attempts"})
- Storage: $storageResult
- Duration: $([math]::Round($agentElapsed.TotalSeconds, 1))s

## Files Created

- ``memory/sessions/session_$sessionTimestamp.md``

## Current System Status

$(if ($agentSuccess) {'Operational — agent running, data stored.'} else {"Error state — $agentError"})

## Continuation Instructions

$(if ($agentSuccess) {'System operational. Next run will be triggered by scheduled task or manual execution.'} else {'Check logs/system.log for details. Run .\scripts\run_scraper.ps1 to retry.'})
"@

$sessionContent | Set-Content $sessionFile -Encoding utf8
Write-Log "Session log: $sessionFile"

Write-Log "========== SCRAPER SESSION COMPLETE =========="
