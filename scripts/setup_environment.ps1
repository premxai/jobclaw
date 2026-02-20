<#
.SYNOPSIS
    Environment verification and setup for AI Job Agent.
.DESCRIPTION
    Verifies OpenClaw is installed, MiniMax provider is configured,
    required directories exist, and creates any missing ones.
    Logs environment status to logs/system.log.
#>

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $ProjectRoot) { $ProjectRoot = (Get-Location).Path }

# ── Logging helper ────────────────────────────────────────────────────
$LogFile = Join-Path $ProjectRoot "logs\system.log"

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $entry = "$timestamp | $Level | $Message"
    Write-Host $entry
    # Ensure logs directory exists
    $logDir = Split-Path $LogFile -Parent
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
    Add-Content -Path $LogFile -Value $entry
}

Write-Log "========== ENVIRONMENT SETUP START =========="

# ── 1. Verify OpenClaw ────────────────────────────────────────────────
Write-Log "Checking OpenClaw installation..."
$openclawCmd = Get-Command "openclaw" -ErrorAction SilentlyContinue
if ($openclawCmd) {
    $openclawVersion = & openclaw --version 2>&1
    Write-Log "OpenClaw found: $openclawVersion"
} else {
    Write-Log "OpenClaw NOT found. Install with: npm install -g openclaw@latest" "WARN"
    Write-Log "Continuing setup — OpenClaw is required for agent execution." "WARN"
}

# ── 2. Verify MiniMax Provider ────────────────────────────────────────
Write-Log "Checking MiniMax M2.5 provider configuration..."
$minimaxKeyExists = $false

# Check environment variable
if ($env:MINIMAX_API_KEY) {
    Write-Log "MINIMAX_API_KEY found in environment."
    $minimaxKeyExists = $true
}

# Check .env file
$envFile = Join-Path $ProjectRoot ".env"
if (Test-Path $envFile) {
    $envContent = Get-Content $envFile -Raw
    if ($envContent -match "MINIMAX_API_KEY=\S+") {
        Write-Log "MINIMAX_API_KEY found in .env file."
        $minimaxKeyExists = $true
    }
}

if (-not $minimaxKeyExists) {
    Write-Log "MINIMAX_API_KEY not configured. Set it in .env or as environment variable." "WARN"
    Write-Log "Get your key at: https://platform.minimax.io" "WARN"
}

# ── 3. Verify & Create Directories ───────────────────────────────────
Write-Log "Verifying directory structure..."
$requiredDirs = @(
    "agents",
    "scripts",
    "scripts\utils",
    "config",
    "data",
    "logs",
    "state",
    "memory\sessions",
    "memory\checkpoints",
    "memory\summaries"
)

$dirsCreated = 0
foreach ($dir in $requiredDirs) {
    $fullPath = Join-Path $ProjectRoot $dir
    if (-not (Test-Path $fullPath)) {
        New-Item -ItemType Directory -Path $fullPath -Force | Out-Null
        Write-Log "Created missing directory: $dir"
        $dirsCreated++
    } else {
        Write-Log "Directory OK: $dir"
    }
}

if ($dirsCreated -eq 0) {
    Write-Log "All directories verified — none missing."
} else {
    Write-Log "Created $dirsCreated missing directories."
}

# ── 4. Verify Critical Files ─────────────────────────────────────────
Write-Log "Verifying critical files..."
$criticalFiles = @(
    "memory\checkpoints\system_checkpoint.json",
    "memory\summaries\system_summary.md",
    "README.md"
)

foreach ($file in $criticalFiles) {
    $fullPath = Join-Path $ProjectRoot $file
    if (Test-Path $fullPath) {
        Write-Log "File OK: $file"
    } else {
        Write-Log "Missing critical file: $file" "WARN"
    }
}

# ── 5. Verify Python ─────────────────────────────────────────────────
Write-Log "Checking Python installation..."
$pythonCmd = Get-Command "python" -ErrorAction SilentlyContinue
if ($pythonCmd) {
    $pythonVersion = & python --version 2>&1
    Write-Log "Python found: $pythonVersion"
} else {
    Write-Log "Python NOT found. Required for utility scripts." "WARN"
}

# ── 6. Summary ───────────────────────────────────────────────────────
Write-Log "========== ENVIRONMENT STATUS =========="
Write-Log "OpenClaw:     $(if ($openclawCmd) {'INSTALLED'} else {'NOT FOUND'})"
Write-Log "MiniMax Key:  $(if ($minimaxKeyExists) {'CONFIGURED'} else {'NOT SET'})"
Write-Log "Directories:  ALL VERIFIED"
Write-Log "Python:       $(if ($pythonCmd) {'INSTALLED'} else {'NOT FOUND'})"
Write-Log "========== ENVIRONMENT SETUP COMPLETE =========="
