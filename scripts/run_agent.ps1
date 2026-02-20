<#
.SYNOPSIS
    Execute the Google Jobs OpenClaw agent.
.DESCRIPTION
    Initializes OpenClaw, executes the Google Jobs agent, captures results,
    and logs the session. Handles errors gracefully for crash recovery.
#>

param(
    [string]$AgentConfig = "agents\google_jobs_agent.yaml",
    [string]$OutputFile = "data\google_jobs_raw.json",
    [int]$TimeoutSeconds = 120
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $ProjectRoot) { $ProjectRoot = (Get-Location).Path }

$LogFile = Join-Path $ProjectRoot "logs\system.log"

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $entry = "$timestamp | $Level | [run_agent] $Message"
    Write-Host $entry
    $logDir = Split-Path $LogFile -Parent
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
    Add-Content -Path $LogFile -Value $entry
}

# ── Pre-flight checks ────────────────────────────────────────────────
Write-Log "========== AGENT EXECUTION START =========="

$agentPath = Join-Path $ProjectRoot $AgentConfig
if (-not (Test-Path $agentPath)) {
    Write-Log "Agent config not found: $agentPath" "ERROR"
    exit 1
}

$openclawCmd = Get-Command "openclaw" -ErrorAction SilentlyContinue
if (-not $openclawCmd) {
    Write-Log "OpenClaw not installed. Run: npm install -g openclaw@latest" "ERROR"
    exit 1
}

# Ensure output directory
$outputDir = Split-Path (Join-Path $ProjectRoot $OutputFile) -Parent
if (-not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
}

# ── Execute agent ─────────────────────────────────────────────────────
Write-Log "Executing agent: $AgentConfig"
Write-Log "Output target: $OutputFile"
Write-Log "Timeout: ${TimeoutSeconds}s"

$startTime = Get-Date
$outputPath = Join-Path $ProjectRoot $OutputFile

try {
    # Run OpenClaw agent with timeout
    $process = Start-Process -FilePath "openclaw" `
        -ArgumentList "run", $agentPath `
        -NoNewWindow -PassThru -RedirectStandardOutput $outputPath `
        -RedirectStandardError (Join-Path $ProjectRoot "logs\agent_stderr.log")

    $completed = $process.WaitForExit($TimeoutSeconds * 1000)

    if (-not $completed) {
        $process.Kill()
        Write-Log "Agent execution timed out after ${TimeoutSeconds}s" "ERROR"
        exit 1
    }

    if ($process.ExitCode -ne 0) {
        Write-Log "Agent exited with code: $($process.ExitCode)" "ERROR"
        exit 1
    }

    $elapsed = (Get-Date) - $startTime
    Write-Log "Agent completed in $([math]::Round($elapsed.TotalSeconds, 1))s"

    # Verify output
    if (Test-Path $outputPath) {
        $fileSize = (Get-Item $outputPath).Length
        Write-Log "Output file: $outputPath ($fileSize bytes)"
    } else {
        Write-Log "No output file generated" "WARN"
    }

} catch {
    Write-Log "Agent execution failed: $_" "ERROR"
    exit 1
}

Write-Log "========== AGENT EXECUTION COMPLETE =========="
