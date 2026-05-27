$ErrorActionPreference = "Stop"

$SourceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $SourceRoot
Set-Location $SourceRoot
$RootInternal = Join-Path $RepoRoot "_internal"
$RootAlertSounds = Join-Path $RepoRoot "alert_sounds"

function Stop-OneClickProcesses {
    param([string]$RootPath)

    if (-not $RootPath) {
        return
    }
    $rootFullPath = [System.IO.Path]::GetFullPath($RootPath)
    Get-CimInstance Win32_Process |
        Where-Object {
            ($_.Name -eq "MapleAlert.exe" -and $_.ExecutablePath -and [System.IO.Path]::GetFullPath($_.ExecutablePath).StartsWith($rootFullPath, [System.StringComparison]::OrdinalIgnoreCase)) -or
            ($_.Name -in @("cmd.exe", "powershell.exe", "pwsh.exe") -and $_.CommandLine -and $_.CommandLine.IndexOf((Join-Path $rootFullPath "START_MAPLE_ALERT.bat"), [System.StringComparison]::OrdinalIgnoreCase) -ge 0)
        } |
        ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    Start-Sleep -Milliseconds 500
}

$Venv = Join-Path $RepoRoot ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $Python)) {
    py -m venv $Venv
}

& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements.txt
& $Python -m pip install pyinstaller

if (Test-Path ".\build") {
    Remove-Item -LiteralPath ".\build" -Recurse -Force
}
if (Test-Path ".\dist\MapleAlert") {
    Remove-Item -LiteralPath ".\dist\MapleAlert" -Recurse -Force
}
if (Test-Path ".\MapleAlert.spec") {
    Remove-Item -LiteralPath ".\MapleAlert.spec" -Force
}

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --name MapleAlert `
    --onedir `
    --console `
    --collect-submodules cv2 `
    .\maple_alert.py

Stop-OneClickProcesses $RepoRoot
Copy-Item ".\dist\MapleAlert\MapleAlert.exe" $RepoRoot -Force
Copy-Item ".\config.example.toml" (Join-Path $RepoRoot "config.toml") -Force
if (Test-Path $RootInternal) {
    Remove-Item -LiteralPath $RootInternal -Recurse -Force
}
Copy-Item ".\dist\MapleAlert\_internal" $RepoRoot -Recurse -Force
Copy-Item ".\watchdog_supervisor.ps1" (Join-Path $RootInternal "watchdog_supervisor.ps1") -Force
if (Test-Path $RootAlertSounds) {
    Remove-Item -LiteralPath $RootAlertSounds -Recurse -Force
}
& $Python .\maple_alert.py `
    --config (Join-Path $RepoRoot "config.toml") `
    --export-alert-wavs $RootAlertSounds

Write-Host ""
Write-Host "Repo root one-click files updated:"
Write-Host $RepoRoot
Write-Host ""
Write-Host "Use START_MAPLE_ALERT.bat from the repo root."
