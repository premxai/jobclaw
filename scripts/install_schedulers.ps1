<#
.SYNOPSIS
    Installs Windows Scheduled Tasks for the JobClaw micro-scrapers.
.DESCRIPTION
    Registers OS-level tasks instead of relying on a Python loop.
    1. JobClaw_ATS_Scraper (runs scrape_ats.py every 30 minutes)
    2. JobClaw_RSS_Scraper (runs scrape_rss.py every 60 minutes)
#>

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $ProjectRoot) { $ProjectRoot = (Get-Location).Path }

function Register-MicroScraper {
    param(
        [string]$TaskName,
        [string]$PythonScript,
        [int]$MinutesInterval,
        [string]$Description
    )
    
    $ScriptPath = Join-Path $ProjectRoot $PythonScript
    Write-Host "Registering $TaskName ($MinutesInterval min interval)"
    
    # Remove existing
    $existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existingTask) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }

    # Action: Run Python headlessly
    $action = New-ScheduledTaskAction `
        -Execute "python.exe" `
        -Argument "`"$ScriptPath`"" `
        -WorkingDirectory $ProjectRoot

    # Trigger
    $trigger = New-ScheduledTaskTrigger `
        -Once `
        -At (Get-Date).AddMinutes(1) `
        -RepetitionInterval (New-TimeSpan -Minutes $MinutesInterval) `
        -RepetitionDuration (New-TimeSpan -Days 3650) # 10 years

    # Settings
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -MultipleInstances IgnoreNew
        
    $principal = New-ScheduledTaskPrincipal `
        -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
        -LogonType Interactive `
        -RunLevel Highest
        
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description $Description `
        -Force | Out-Null
        
    Write-Host "✅ $TaskName registered successfully."
}

function Register-DailyTask {
    param(
        [string]$TaskName,
        [string]$PythonScript,
        [string]$TimeOfDay,  # e.g., "23:00"
        [string]$Description
    )
    
    $ScriptPath = Join-Path $ProjectRoot $PythonScript
    Write-Host "Registering $TaskName (daily at $TimeOfDay)"
    
    # Remove existing
    $existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existingTask) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }

    # Action: Run Python headlessly
    $action = New-ScheduledTaskAction `
        -Execute "python.exe" `
        -Argument "`"$ScriptPath`"" `
        -WorkingDirectory $ProjectRoot

    # Daily trigger at specified time
    $trigger = New-ScheduledTaskTrigger -Daily -At $TimeOfDay

    # Settings
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -MultipleInstances IgnoreNew
        
    $principal = New-ScheduledTaskPrincipal `
        -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
        -LogonType Interactive `
        -RunLevel Highest
        
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description $Description `
        -Force | Out-Null
        
    Write-Host "✅ $TaskName registered successfully."
}

Write-Host "========== JOBCLAW SCHEDULER INSTALL =========="
Register-MicroScraper -TaskName "JobClaw_ATS_Scraper" -PythonScript "scripts\ingestion\scrape_ats.py" -MinutesInterval 30 -Description "Scrapes Greenhouse, Lever, Workday APIs"
Register-MicroScraper -TaskName "JobClaw_RSS_Scraper" -PythonScript "scripts\ingestion\scrape_rss.py" -MinutesInterval 60 -Description "Scrapes Aggregator RSS Feeds"
Register-MicroScraper -TaskName "JobClaw_GitHub_Scraper" -PythonScript "scripts\ingestion\scrape_github.py" -MinutesInterval 120 -Description "Scrapes GitHub Markdown tables"
Register-MicroScraper -TaskName "JobClaw_OpenClaw_Scraper" -PythonScript "scripts\ingestion\scrape_openclaw.py" -MinutesInterval 240 -Description "Browser Automation Bypass"
Register-DailyTask -TaskName "JobClaw_Discovery" -PythonScript "scripts\discovery\run_daily_discovery.py" -TimeOfDay "23:00" -Description "Daily ATS company discovery via Brave Search"
Write-Host "========== SCHEDULER INSTALLATION COMPLETE =========="
Write-Host "Note: To run the discord bot, please run 'python scripts/discord_bot.py' in a separate terminal."
