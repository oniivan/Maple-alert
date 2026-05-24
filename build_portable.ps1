$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$Portable = Join-Path $Root "dist\MapleAlertPortable"

function Stop-PortableProcesses {
    param([string]$PortablePath)

    if (-not $PortablePath) {
        return
    }
    $portableFullPath = [System.IO.Path]::GetFullPath($PortablePath)
    Get-CimInstance Win32_Process |
        Where-Object {
            ($_.ExecutablePath -and [System.IO.Path]::GetFullPath($_.ExecutablePath).StartsWith($portableFullPath, [System.StringComparison]::OrdinalIgnoreCase)) -or
            ($_.CommandLine -and $_.CommandLine.IndexOf($portableFullPath, [System.StringComparison]::OrdinalIgnoreCase) -ge 0)
        } |
        ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    Start-Sleep -Milliseconds 500
}

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    py -m venv .venv
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
Copy-Item ".\README.md" $Portable -Force
Copy-Item ".\README_FIRST.txt" $Portable -Force
Copy-Item ".\START_MAPLE_ALERT.bat" $Portable -Force
Copy-Item ".\watchdog_supervisor.ps1" (Join-Path $Portable "_internal\watchdog_supervisor.ps1") -Force

& $Python .\maple_alert.py `
    --config (Join-Path $Portable "config.toml") `
    --export-alert-wavs (Join-Path $Portable "alert_sounds")

$Zip = Join-Path $Root "dist\MapleAlertPortable.zip"
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
