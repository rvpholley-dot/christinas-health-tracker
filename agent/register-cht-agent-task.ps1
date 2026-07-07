# register-cht-agent-task.ps1
# One-time setup: register a Windows Scheduled Task that auto-starts the
# cht-agent service at logon (mirrors the n8n-native-agency task pattern).
#
# Run once:  .\register-cht-agent-task.ps1
#
# Notes:
# - RunLevel Limited + AtLogOn => runs in Brian's interactive session.
# - ExecutionTimeLimit 0 => never auto-killed; this is a long-lived service.
# - Reminders only fire while the PC is on/awake (logon auto-start cannot
#   wake a sleeping machine).

$ErrorActionPreference = "Stop"

$script = "D:\Users\brian\Projects\Personal\christinas-health-tracker\agent\start-cht-agent.ps1"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`""

$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERNAME"

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName "cht-agent" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -RunLevel Limited `
    -Force `
    -Description "Christina's health tracker agent: PWA API on 127.0.0.1:8765 (tailnet :8446), Telegram chat loop, missed-dose reminders. Data/secrets on D:\Christina."

Write-Host "Registered scheduled task 'cht-agent'. It will start at next logon."
Write-Host "To start it now:  Start-ScheduledTask -TaskName 'cht-agent'"
