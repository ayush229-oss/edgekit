# Install Edgekit frontend + backend as auto-restart scheduled tasks.
# Must be run elevated.
$ErrorActionPreference = "Stop"

$user = "$env:USERDOMAIN\$env:USERNAME"

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 99 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0)

$trigger = New-ScheduledTaskTrigger -AtLogOn

# Backend
$beCmd = 'Set-Location C:\Users\Ayush\projects\edgekit; python -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8765'
$beAction = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -Command `"$beCmd`""
Register-ScheduledTask `
    -TaskName "EdgekitBackend" `
    -Description "Edgekit FastAPI backend (auto-start at logon, auto-restart on failure)" `
    -Action $beAction -Trigger $trigger -Settings $settings `
    -User $user -RunLevel Highest -Force | Out-Null

# Frontend
$feCmd = 'Set-Location C:\Users\Ayush\projects\edgekit\frontend; npx next dev -p 3000'
$feAction = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -Command `"$feCmd`""
Register-ScheduledTask `
    -TaskName "EdgekitFrontend" `
    -Description "Edgekit Next.js frontend (auto-start at logon, auto-restart on failure)" `
    -Action $feAction -Trigger $trigger -Settings $settings `
    -User $user -RunLevel Highest -Force | Out-Null

Start-ScheduledTask -TaskName "EdgekitBackend"
Start-Sleep -Seconds 4
Start-ScheduledTask -TaskName "EdgekitFrontend"

Write-Host "Tasks registered:"
Get-ScheduledTask -TaskName "Edgekit*" | Select-Object TaskName, State
