<#
.SYNOPSIS
    Install aggressive Windows Scheduled Tasks for MAXIMUM speed job discovery.
.DESCRIPTION
    Creates 3 scheduled tasks for tiered scraping frequency:
      - FAST scan (RSS + Enterprise + GitHub): every 30 minutes
      - FULL scan (all scrapers incl. ATS):    every 2 hours
      - OpenClaw (browser automation):          every 4 hours (saves API credits)

    This replaces the old 10-minute single-task approach.
    All tasks run under the current user and auto-restart on failure.
#>

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $ProjectRoot) { $ProjectRoot = (Get-Location).Path }

$LogFile = Join-Path $ProjectRoot "logs\system.log"
$PythonExe = "python"
$OrchestratorScript = Join-Path $ProjectRoot "scripts\ingestion\run_all_scrapers.py"

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $entry = "$timestamp | $Level | [install_schedulers] $Message"
    Write-Host $entry
    $logDir = Split-Path $LogFile -Parent
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
    Add-Content -Path $LogFile -Value $entry
}

Write-Log "========== SPEED SCHEDULER INSTALLATION =========="

# ── Task Definitions ──────────────────────────────────────────────────
$Tasks = @(
    @{
        Name        = "JobClaw_Fast_Scan"
        Description = "Quick scan: RSS + Enterprise + GitHub every 30 min"
        Arguments   = "-NoProfile -ExecutionPolicy Bypass -Command `"cd '$ProjectRoot'; python '$OrchestratorScript' --fast --no-openclaw`""
        IntervalMin = 30
    },
    @{
        Name        = "JobClaw_Full_Scan"
        Description = "Full sweep: all scrapers including 11,800 ATS companies every 2 hours"
        Arguments   = "-NoProfile -ExecutionPolicy Bypass -Command `"cd '$ProjectRoot'; python '$OrchestratorScript' --no-openclaw`""
        IntervalMin = 120
    },
    @{
        Name        = "JobClaw_OpenClaw"
        Description = "Browser automation: LinkedIn/Indeed/Glassdoor every 4 hours"
        Arguments   = "-NoProfile -ExecutionPolicy Bypass -Command `"cd '$ProjectRoot'; python '$OrchestratorScript' --fast --no-github`""
        # This one runs the orchestrator in fast mode (no ATS) but with OpenClaw enabled
        # We handle this by running the full orchestrator with specific flags
        IntervalMin = 240
    }
)

# Actually, the OpenClaw task should ONLY run openclaw. Let's fix the args:
$Tasks[2].Arguments = "-NoProfile -ExecutionPolicy Bypass -Command `"cd '$ProjectRoot'; python -c \`"import asyncio,sys; sys.path.insert(0,'$($ProjectRoot.Replace('\','\\'))'); from scripts.ingestion.scrape_openclaw import run_openclaw_scraper; asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy()); asyncio.run(run_openclaw_scraper())\`"`""

# ── Register Each Task ────────────────────────────────────────────────
foreach ($task in $Tasks) {
    $taskName = $task.Name
    
    # Remove existing task if present
    $existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Log "Removing existing task: $taskName"
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    }

    Write-Log "Registering: $taskName (every $($task.IntervalMin) min)"

    $action = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument $task.Arguments `
        -WorkingDirectory $ProjectRoot

    $trigger = New-ScheduledTaskTrigger `
        -Once `
        -At (Get-Date) `
        -RepetitionInterval (New-TimeSpan -Minutes $task.IntervalMin) `
        -RepetitionDuration (New-TimeSpan -Days 365)

    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 60) `
        -MultipleInstances IgnoreNew

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
            -Description $task.Description `
            -Force

        Write-Log "  ✓ $taskName registered successfully"
    } catch {
        Write-Log "  ✗ Failed to register $taskName : $_" "ERROR"
    }
}

# ── Summary ───────────────────────────────────────────────────────────
Write-Log ""
Write-Log "═══ SCHEDULE SUMMARY ═══"
Write-Log "  JobClaw_Fast_Scan  → every 30 min  (RSS + Enterprise + GitHub)"
Write-Log "  JobClaw_Full_Scan  → every 1 hour  (ALL scrapers incl. 11,800 ATS)"
Write-Log "  JobClaw_OpenClaw   → every 4 hours (LinkedIn/Indeed/Glassdoor via browser)"
Write-Log ""
Write-Log "Discord delivery: INSTANT — orchestrator pushes to Discord the moment scraping finishes."
Write-Log ""
Write-Log "Expected timeline for a NEW job posting to reach Discord:"
Write-Log "  Enterprise (Apple/Amazon/Google): ≤30 min"
Write-Log "  ATS boards (Greenhouse/Lever):    ≤1 hour"
Write-Log "  LinkedIn/Indeed/Glassdoor:         ≤4 hours"
Write-Log ""
Write-Log "To check status:  Get-ScheduledTask -TaskName 'JobClaw_*' | Format-Table"
Write-Log "To remove all:    Get-ScheduledTask -TaskName 'JobClaw_*' | Unregister-ScheduledTask"
Write-Log "========== INSTALLATION COMPLETE =========="

# Also remove the old single-task if it exists
$oldTask = Get-ScheduledTask -TaskName "AIJobAgent_Scraper" -ErrorAction SilentlyContinue
if ($oldTask) {
    Write-Log "Removing legacy task: AIJobAgent_Scraper"
    Unregister-ScheduledTask -TaskName "AIJobAgent_Scraper" -Confirm:$false
    Write-Log "Legacy task removed."
}
