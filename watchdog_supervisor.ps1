$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = $ScriptDir
if (-not (Test-Path (Join-Path $Root "MapleAlert.exe")) -and
    (Split-Path -Leaf $Root) -ieq "_internal") {
    $ParentRoot = Split-Path -Parent $Root
    if (Test-Path (Join-Path $ParentRoot "MapleAlert.exe")) {
        $Root = $ParentRoot
    }
}
Set-Location $Root

$Config = ".\config.toml"
$Exe = Join-Path $Root "MapleAlert.exe"
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Script = ".\maple_alert.py"
$Heartbeat = Join-Path $Root "runtime\watchdog_heartbeat.json"
$MonitorHeartbeat = Join-Path $Root "runtime\heartbeat.json"
$QuitRequest = Join-Path $Root "runtime\quit_requested.json"
$LogDir = Join-Path $Root "logs"
$StdOut = Join-Path $LogDir "watchdog_stdout.log"
$StdErr = Join-Path $LogDir "watchdog_stderr.log"
$OverlayStdOut = Join-Path $LogDir "overlay_stdout.log"
$OverlayStdErr = Join-Path $LogDir "overlay_stderr.log"

$CheckIntervalSeconds = 5
$StartupGraceSeconds = 25
$StaleSeconds = 30
$RestartDelaySeconds = 5
$LastMonitorStatusKey = ""
$LastStdOutPosition = 0

function Invoke-SupervisorBeep {
    for ($i = 0; $i -lt 4; $i++) {
        [console]::beep(2200, 180)
        Start-Sleep -Milliseconds 80
    }
}

function Get-TomlBool {
    param(
        [string]$Path,
        [string]$Section,
        [string]$Key,
        [bool]$Default
    )

    if (-not (Test-Path $Path)) {
        return $Default
    }

    $InSection = $false
    foreach ($Line in Get-Content $Path) {
        $Clean = ($Line -replace "#.*$", "").Trim()
        if ($Clean -match "^\[(.+)\]$") {
            $InSection = $Matches[1] -ieq $Section
            continue
        }
        if ($InSection -and $Clean -match ("^{0}\s*=\s*(true|false)\s*$" -f [regex]::Escape($Key))) {
            return $Matches[1] -ieq "true"
        }
    }

    return $Default
}

function Stop-ProcessTree {
    param([int]$ProcessId)

    Get-CimInstance Win32_Process |
        Where-Object { $_.ParentProcessId -eq $ProcessId } |
        ForEach-Object { Stop-ProcessTree -ProcessId ([int]$_.ProcessId) }

    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

function Test-QuitRequested {
    return Test-Path $QuitRequest
}

function Write-NewWatchdogOutput {
    if (-not (Test-Path $StdOut)) {
        return
    }

    try {
        $Reader = $null
        $Stream = [System.IO.File]::Open($StdOut, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
        try {
            if ($script:LastStdOutPosition -gt $Stream.Length) {
                $script:LastStdOutPosition = 0
            }
            [void]$Stream.Seek($script:LastStdOutPosition, [System.IO.SeekOrigin]::Begin)
            $Reader = New-Object System.IO.StreamReader($Stream)
            $Text = $Reader.ReadToEnd()
            $script:LastStdOutPosition = $Stream.Length
        } finally {
            if ($null -ne $Reader) {
                $Reader.Dispose()
            } else {
                $Stream.Dispose()
            }
        }

        if ([string]::IsNullOrWhiteSpace($Text)) {
            return
        }

        foreach ($Line in ($Text -split "`r?`n")) {
            if ([string]::IsNullOrWhiteSpace($Line)) {
                continue
            }
            if ($Line -match "Maple alert:|Maple detection:|cleared|Quit request|Resolution|Detected new resolution|MapleStory") {
                Write-Host $Line
            }
        }
    } catch {
        return
    }
}

function Start-WatchdogProcess {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    Remove-Item -LiteralPath $StdOut -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $StdErr -Force -ErrorAction SilentlyContinue

    if (Test-Path $Exe) {
        return Start-Process `
            -FilePath $Exe `
            -ArgumentList "--config `"$Config`" --watchdog --parent-pid $PID" `
            -WorkingDirectory $Root `
            -WindowStyle Hidden `
            -RedirectStandardOutput $StdOut `
            -RedirectStandardError $StdErr `
            -PassThru
    }

    if (Test-Path $Python) {
        return Start-Process `
            -FilePath $Python `
            -ArgumentList "`"$Script`" --config `"$Config`" --watchdog --parent-pid $PID" `
            -WorkingDirectory $Root `
            -WindowStyle Hidden `
            -RedirectStandardOutput $StdOut `
            -RedirectStandardError $StdErr `
            -PassThru
    }

    throw "Could not find MapleAlert.exe or .venv\Scripts\python.exe."
}

function Start-OverlayProcess {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

    if (Test-Path $Exe) {
        return Start-Process `
            -FilePath $Exe `
            -ArgumentList "--config `"$Config`" --overlay --parent-pid $PID" `
            -WorkingDirectory $Root `
            -WindowStyle Hidden `
            -RedirectStandardOutput $OverlayStdOut `
            -RedirectStandardError $OverlayStdErr `
            -PassThru
    }

    if (Test-Path $Python) {
        return Start-Process `
            -FilePath $Python `
            -ArgumentList "`"$Script`" --config `"$Config`" --overlay --parent-pid $PID" `
            -WorkingDirectory $Root `
            -WindowStyle Hidden `
            -RedirectStandardOutput $OverlayStdOut `
            -RedirectStandardError $OverlayStdErr `
            -PassThru
    }

    return $null
}

function Update-OverlayProcess {
    param($Overlay)

    $OverlayEnabled = Get-TomlBool -Path $Config -Section "overlay" -Key "enabled" -Default $true
    if ($OverlayEnabled) {
        if ($null -eq $Overlay -or $Overlay.HasExited) {
            $Overlay = Start-OverlayProcess
            if ($null -ne $Overlay) {
                Write-Host ("Started heartbeat overlay pid={0}" -f $Overlay.Id)
            }
        }
    } elseif ($null -ne $Overlay -and -not $Overlay.HasExited) {
        Stop-ProcessTree -ProcessId $Overlay.Id
        $Overlay = $null
    }

    return $Overlay
}

function Write-MonitorStatusChanges {
    if (-not (Test-Path $MonitorHeartbeat)) {
        return
    }

    try {
        $Payload = Get-Content -LiteralPath $MonitorHeartbeat -Raw | ConvertFrom-Json
        if ($null -eq $Payload -or $null -eq $Payload.rect) {
            return
        }

        $Source = [string]$Payload.source
        $Width = [int]$Payload.rect.width
        $Height = [int]$Payload.rect.height
        $TargetWindow = [bool]$Payload.target_window
        $MapleDetected = -not $TargetWindow -or ($Source -ieq "window")
        $StatusKey = "{0}|{1}x{2}|{3}" -f $Source, $Width, $Height, $MapleDetected

        if ($StatusKey -eq $script:LastMonitorStatusKey) {
            return
        }

        $PreviousKey = $script:LastMonitorStatusKey
        $script:LastMonitorStatusKey = $StatusKey

        if ($TargetWindow -and -not $MapleDetected) {
            Write-Host ("MapleStory not detected; using monitor fallback at resolution {0}x{1}." -f $Width, $Height) -ForegroundColor Red
            return
        }

        if ($TargetWindow -and $MapleDetected -and ($PreviousKey -eq "" -or $PreviousKey -match "\|False$")) {
            Write-Host ("MapleStory detected; using window capture at resolution {0}x{1}." -f $Width, $Height) -ForegroundColor Green
            return
        }

        Write-Host ("Detected new resolution {0}x{1}; capture source={2}." -f $Width, $Height, $Source) -ForegroundColor Cyan
    } catch {
        return
    }
}

Write-Host "Maple Alert outer supervisor is running."
Write-Host "It will restart the watchdog if the watchdog exits or stops updating $Heartbeat."
Write-Host "Close this window to stop monitoring."
Write-Host ""
Remove-Item -LiteralPath $QuitRequest -Force -ErrorAction SilentlyContinue

$RestartCount = 0
$Overlay = $null
$Watchdog = $null
$QuitRequested = $false
try {
    while (-not $QuitRequested) {
        Remove-Item -LiteralPath $Heartbeat -Force -ErrorAction SilentlyContinue

        $Overlay = Update-OverlayProcess -Overlay $Overlay
        $Watchdog = Start-WatchdogProcess
        $script:LastStdOutPosition = 0
        $StartedAt = Get-Date
        Write-Host ("Started watchdog pid={0}" -f $Watchdog.Id)

        while ($true) {
            Start-Sleep -Seconds $CheckIntervalSeconds
            Write-NewWatchdogOutput
            if (Test-QuitRequested) {
                $QuitRequested = $true
                Write-Host "Quit requested from overlay. Stopping Maple Alert..."
                break
            }
            $Watchdog.Refresh()
            $Overlay = Update-OverlayProcess -Overlay $Overlay
            Write-MonitorStatusChanges

            if ($Watchdog.HasExited) {
                $RestartCount += 1
                Write-Host ("Watchdog exited with code {0}. Restarting in {1}s. restart #{2}" -f $Watchdog.ExitCode, $RestartDelaySeconds, $RestartCount)
                Invoke-SupervisorBeep
                break
            }

            if (Test-Path $Heartbeat) {
                $AgeSeconds = ((Get-Date) - (Get-Item $Heartbeat).LastWriteTime).TotalSeconds
                if ($AgeSeconds -gt $StaleSeconds) {
                    $RestartCount += 1
                    Write-Host ("Watchdog heartbeat is stale ({0:N1}s old). Restarting in {1}s. restart #{2}" -f $AgeSeconds, $RestartDelaySeconds, $RestartCount)
                    Invoke-SupervisorBeep
                    Stop-ProcessTree -ProcessId $Watchdog.Id
                    break
                }
            } elseif (((Get-Date) - $StartedAt).TotalSeconds -gt $StartupGraceSeconds) {
                $RestartCount += 1
                Write-Host ("Watchdog did not write a heartbeat after {0}s. Restarting in {1}s. restart #{2}" -f $StartupGraceSeconds, $RestartDelaySeconds, $RestartCount)
                Invoke-SupervisorBeep
                Stop-ProcessTree -ProcessId $Watchdog.Id
                break
            }
        }

        if ($QuitRequested) {
            break
        }
        Start-Sleep -Seconds $RestartDelaySeconds
    }
}
finally {
    Write-Host "Stopping Maple Alert child processes..."
    if ($null -ne $Overlay -and -not $Overlay.HasExited) {
        Stop-ProcessTree -ProcessId $Overlay.Id
    }
    if ($null -ne $Watchdog -and -not $Watchdog.HasExited) {
        Stop-ProcessTree -ProcessId $Watchdog.Id
    }
}
