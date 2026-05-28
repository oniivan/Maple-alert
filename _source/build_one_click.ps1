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

function Get-GitText {
    param([string[]]$Arguments)

    try {
        $Output = & git @Arguments 2>$null
        if ($LASTEXITCODE -eq 0 -and $null -ne $Output) {
            return (($Output -join "`n").Trim())
        }
    } catch {
    }
    return ""
}

function Get-AppVersion {
    param([string]$SourceFile)

    $Line = Select-String -Path $SourceFile -Pattern '^APP_VERSION\s*=\s*"([^"]+)"' | Select-Object -First 1
    if ($Line -and $Line.Matches.Count -gt 0) {
        return $Line.Matches[0].Groups[1].Value
    }
    return "unknown"
}

function Get-SourceDirtyText {
    $IgnoredOutputs = @(
        ":(exclude)MapleAlert.exe",
        ":(exclude)_internal",
        ":(exclude)alert_sounds",
        ":(exclude)config.toml",
        ":(exclude)release_manifest.json",
        ":(exclude)SHA256SUMS.txt",
        ":(exclude)_source/build",
        ":(exclude)_source/dist",
        ":(exclude)_source/MapleAlert.spec"
    )
    $Arguments = @("status", "--short", "--untracked-files=no", "--", ".") + $IgnoredOutputs
    return Get-GitText $Arguments
}

function Get-ReleaseFileEntry {
    param(
        [string]$RootPath,
        [string]$RelativePath
    )

    $FullPath = Join-Path $RootPath $RelativePath
    $Item = Get-Item -LiteralPath $FullPath
    $Hash = Get-FileHash -LiteralPath $FullPath -Algorithm SHA256
    return [ordered]@{
        path = ($RelativePath -replace "\\", "/")
        bytes = [int64]$Item.Length
        sha256 = $Hash.Hash.ToUpperInvariant()
    }
}

function Write-ReleaseProvenance {
    param(
        [string]$RepoRoot,
        [string]$SourceRoot,
        [string]$PythonPath,
        [string]$InternalPath,
        [string]$AlertSoundsPath
    )

    $AppVersion = Get-AppVersion (Join-Path $SourceRoot "maple_alert.py")
    $Commit = Get-GitText @("rev-parse", "HEAD")
    $Status = Get-SourceDirtyText
    $PythonVersion = (& $PythonPath --version) 2>&1
    $PyInstallerVersion = (& $PythonPath -m PyInstaller --version) 2>&1

    $RelativeFiles = New-Object System.Collections.Generic.List[string]
    foreach ($Path in @(
        "START_MAPLE_ALERT.bat",
        "MapleAlert.exe",
        "config.toml",
        "README.md",
        "README_FIRST.txt",
        "_internal\watchdog_supervisor.ps1"
    )) {
        if (Test-Path (Join-Path $RepoRoot $Path)) {
            [void]$RelativeFiles.Add($Path)
        }
    }
    if (Test-Path $AlertSoundsPath) {
        Get-ChildItem -LiteralPath $AlertSoundsPath -File |
            Sort-Object Name |
            ForEach-Object {
                [void]$RelativeFiles.Add((Join-Path "alert_sounds" $_.Name))
            }
    }

    $Entries = @()
    foreach ($RelativePath in $RelativeFiles) {
        $Entries += Get-ReleaseFileEntry -RootPath $RepoRoot -RelativePath $RelativePath
    }

    $Manifest = [ordered]@{
        app_name = "Maple Alert"
        app_version = $AppVersion
        built_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        source_commit = $Commit
        source_dirty = -not [string]::IsNullOrWhiteSpace($Status)
        python = (($PythonVersion -join "`n").Trim())
        pyinstaller = (($PyInstallerVersion -join "`n").Trim())
        files = $Entries
    }

    $ManifestPath = Join-Path $RepoRoot "release_manifest.json"
    $SumsPath = Join-Path $RepoRoot "SHA256SUMS.txt"
    $Utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($ManifestPath, ($Manifest | ConvertTo-Json -Depth 5), $Utf8NoBom)
    $SumsText = ($Entries | ForEach-Object { "{0}  {1}" -f $_.sha256, $_.path }) -join "`n"
    [System.IO.File]::WriteAllText($SumsPath, ($SumsText + "`n"), $Utf8NoBom)
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

Write-ReleaseProvenance `
    -RepoRoot $RepoRoot `
    -SourceRoot $SourceRoot `
    -PythonPath $Python `
    -InternalPath $RootInternal `
    -AlertSoundsPath $RootAlertSounds

Write-Host ""
Write-Host "Repo root one-click files updated:"
Write-Host $RepoRoot
Write-Host ""
Write-Host "Use START_MAPLE_ALERT.bat from the repo root."
