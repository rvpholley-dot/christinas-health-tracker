# start-cht-agent.ps1
# Launch the cht-agent service (Christina's health tracker agent).
#
# Run automatically at logon via register-cht-agent-task.ps1. The service:
#   · serves the PWA HTTP API on 127.0.0.1:8765
#     (exposed tailnet-only via: tailscale serve --bg --https=8446 http://127.0.0.1:8765)
#   · long-polls Telegram for chat (outbound only, works without the tailnet)
#   · runs the missed-dose reminder loop
#
# Config with secrets lives at D:\Christina\cht-agent\config.json (NOT in git).
# Logs rotate at D:\Christina\cht-agent\agent.log.

$ErrorActionPreference = "Stop"

# Do NOT set $env:TZ here: Windows' CRT can't parse IANA names like
# "America/Denver" and Python silently falls back to UTC. The machine's
# own timezone (Denver) is what gives us correct local-naive timestamps.

$python = "C:\Python313\python.exe"
$agentDir = "D:\Users\brian\Projects\Personal\christinas-health-tracker\agent"

# Ensure the data folders exist (idempotent). Secrets/data stay on D:\Christina.
New-Item -ItemType Directory -Force -Path "D:\Christina\cht-agent" | Out-Null
New-Item -ItemType Directory -Force -Path "D:\Christina\health-log" | Out-Null

Set-Location $agentDir

# Restart forever: a crash must not leave Christina without reminders.
while ($true) {
    # Single-instance guard: clear any orphaned cht_agent.py first. Task
    # Scheduler's Stop kills only this launcher, leaving python holding
    # port 8765 — without this, a restarted task crash-loops on the bind.
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -match 'cht_agent\.py' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

    & $python "$agentDir\cht_agent.py"
    Add-Content -Path "D:\Christina\cht-agent\agent.log" -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ERROR launcher: cht_agent.py exited (code $LASTEXITCODE); restarting in 15s"
    Start-Sleep -Seconds 15
}
