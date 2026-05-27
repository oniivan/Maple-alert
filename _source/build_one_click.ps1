$ErrorActionPreference = "Stop"

$SourceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $SourceRoot
Set-Location $SourceRoot
$Portable = Join-Path $RepoRoot "dist\MapleAlertPortable"
$RootInternal = Join-Path $RepoRoot "_internal"
$RootAlertSounds = Join-Path $RepoRoot "alert_sounds"

function Stop-PortableProcesses {
    param([string]$PortablePath)

    if (-not $PortablePath) {
        return
    }
    $portableFullPath = [System.IO.Path]::GetFullPath($PortablePath)
    Get-CimInstance Win32_Process |
        Where-Object {
            ($_.Name -eq "MapleAlert.exe" -and $_.ExecutablePath -and [System.IO.Path]::GetFullPath($_.ExecutablePath).StartsWith($portableFullPath, [System.StringComparison]::OrdinalIgnoreCase)) -or
            ($_.Name -in @("cmd.exe", "powershell.exe", "pwsh.exe") -and $_.CommandLine -and $_.CommandLine.IndexOf((Join-Path $portableFullPath "START_MAPLE_ALERT.bat"), [System.StringComparison]::OrdinalIgnoreCase) -ge 0)
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

if (Test-Path $Portable) {
    Stop-PortableProcesses $Portable
    Remove-Item -LiteralPath $Portable -Recurse -Force
}
New-Item -ItemType Directory -Path $Portable | Out-Null

Copy-Item -Path ".\dist\MapleAlert\*" -Destination $Portable -Recurse -Force
Copy-Item ".\config.example.toml" (Join-Path $Portable "config.toml") -Force
Copy-Item (Join-Path $RepoRoot "README.md") $Portable -Force
Copy-Item (Join-Path $RepoRoot "README_FIRST.txt") $Portable -Force
Copy-Item (Join-Path $RepoRoot "START_MAPLE_ALERT.bat") $Portable -Force
Copy-Item ".\watchdog_supervisor.ps1" (Join-Path $Portable "_internal\watchdog_supervisor.ps1") -Force

& $Python .\maple_alert.py `
    --config (Join-Path $Portable "config.toml") `
    --export-alert-wavs (Join-Path $Portable "alert_sounds")

$Zip = Join-Path $RepoRoot "dist\MapleAlertPortable.zip"
if (Test-Path $Zip) {
    Remove-Item -LiteralPath $Zip -Force
}
Compress-Archive -Path (Join-Path $Portable "*") -DestinationPath $Zip -Force

Write-Host ""
Write-Host "Portable folder created:"
Write-Host $Portable
Write-Host ""
Write-Host "Transfer zip created:"
Write-Host $Zip

Stop-PortableProcesses $RepoRoot
Copy-Item (Join-Path $Portable "MapleAlert.exe") $RepoRoot -Force
Copy-Item (Join-Path $Portable "config.toml") $RepoRoot -Force
if (Test-Path $RootInternal) {
    Remove-Item -LiteralPath $RootInternal -Recurse -Force
}
Copy-Item (Join-Path $Portable "_internal") $RepoRoot -Recurse -Force
if (Test-Path $RootAlertSounds) {
    Remove-Item -LiteralPath $RootAlertSounds -Recurse -Force
}
Copy-Item (Join-Path $Portable "alert_sounds") $RepoRoot -Recurse -Force

Write-Host ""
Write-Host "Repo root portable files updated for GitHub ZIP downloads."
