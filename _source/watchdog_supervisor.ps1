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
$LogDir = Join-Path $Root "logs"
$StdOut = Join-Path $LogDir "watchdog_stdout.log"
$StdErr = Join-Path $LogDir "watchdog_stderr.log"
$OverlayStdOut = Join-Path $LogDir "overlay_stdout.log"
$OverlayStdErr = Join-Path $LogDir "overlay_stderr.log"

function Get-NowStamp {
    return (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
}

function Get-EpochSeconds {
    return ([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() / 1000.0)
}

function Write-TimestampedHost {
    param(
        [string]$Message,
        [string]$ForegroundColor = ""
    )

    $Stamped = "[{0}] {1}" -f (Get-NowStamp), $Message
    if ([string]::IsNullOrWhiteSpace($ForegroundColor)) {
        Write-Host $Stamped
    } else {
        Write-Host $Stamped -ForegroundColor $ForegroundColor
    }
}

function Write-ForwardedLine {
    param([string]$Line)

    if ($Line -match "^\[\d{4}-\d{2}-\d{2} " -or $Line -match "^\d{4}-\d{2}-\d{2} ") {
        Write-Host $Line
        return
    }
    Write-TimestampedHost $Line
}

function Invoke-SupervisorBeep {
    try {
        for ($i = 0; $i -lt 4; $i++) {
            [console]::beep(2200, 180)
            Start-Sleep -Milliseconds 80
        }
    } catch {
        return
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

function Get-TomlNumber {
    param(
        [string]$Path,
        [string]$Section,
        [string]$Key,
        [double]$Default
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
        if ($InSection -and $Clean -match ("^{0}\s*=\s*(-?\d+(?:\.\d+)?)\s*$" -f [regex]::Escape($Key))) {
            return [double]$Matches[1]
        }
    }

    return $Default
}

function Get-TomlString {
    param(
        [string]$Path,
        [string]$Section,
        [string]$Key,
        [string]$Default
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
        if ($InSection -and $Clean -match ("^{0}\s*=\s*`"([^`"]*)`"\s*$" -f [regex]::Escape($Key))) {
            return $Matches[1]
        }
    }

    return $Default
}

function Resolve-ConfigPathValue {
    param([string]$Value)

    if ([System.IO.Path]::IsPathRooted($Value)) {
        return $Value
    }
    return Join-Path $Root $Value
}

$Heartbeat = Resolve-ConfigPathValue (Get-TomlString -Path $Config -Section "watchdog" -Key "watchdog_heartbeat_file" -Default "runtime/watchdog_heartbeat.json")
$MonitorHeartbeat = Resolve-ConfigPathValue (Get-TomlString -Path $Config -Section "watchdog" -Key "heartbeat_file" -Default "runtime/heartbeat.json")
$SupervisorHeartbeat = Resolve-ConfigPathValue (Get-TomlString -Path $Config -Section "watchdog" -Key "supervisor_heartbeat_file" -Default "runtime/supervisor_heartbeat.json")
$QuitRequest = Resolve-ConfigPathValue (Get-TomlString -Path $Config -Section "watchdog" -Key "quit_file" -Default "runtime/quit_requested.json")

$CheckIntervalSeconds = [Math]::Max(1.0, (Get-TomlNumber -Path $Config -Section "watchdog" -Key "check_interval_seconds" -Default 5.0))
$StartupGraceSeconds = [Math]::Max(1.0, (Get-TomlNumber -Path $Config -Section "watchdog" -Key "startup_grace_seconds" -Default 25.0))
$StaleSeconds = [Math]::Max(2.0, (Get-TomlNumber -Path $Config -Section "watchdog" -Key "stale_seconds" -Default 30.0))
$RestartDelaySeconds = [Math]::Max(0.0, (Get-TomlNumber -Path $Config -Section "watchdog" -Key "restart_delay_seconds" -Default 5.0))
$CrashWindowSeconds = [Math]::Max(30.0, (Get-TomlNumber -Path $Config -Section "watchdog" -Key "crash_window_seconds" -Default 300.0))
$CrashAlertCount = [Math]::Max(1, [int](Get-TomlNumber -Path $Config -Section "watchdog" -Key "crash_alert_count" -Default 5.0))
$WatchdogDownAlertSeconds = [Math]::Max(10.0, (Get-TomlNumber -Path $Config -Section "watchdog" -Key "monitor_down_alert_seconds" -Default 120.0))
$WatchdogRealertSeconds = [Math]::Max(60.0, (Get-TomlNumber -Path $Config -Section "watchdog" -Key "watchdog_realert_seconds" -Default 120.0))
$HealthyClearSeconds = [Math]::Max(10.0, (Get-TomlNumber -Path $Config -Section "watchdog" -Key "healthy_clear_seconds" -Default 600.0))
$SleepSilenceSeconds = [Math]::Max(60.0, (Get-TomlNumber -Path $Config -Section "watchdog" -Key "sleep_silence_seconds" -Default 3600.0))

$LastMonitorStatusKey = ""
$LastStdOutPosition = 0
$SupervisorEvents = New-Object System.Collections.ArrayList
$SupervisorUnavailableSince = $null
$SupervisorUnhealthySince = $null
$SupervisorHealthySince = $null
$SupervisorLatchedTitle = ""
$SupervisorLatchedReason = ""
$SupervisorLatchedCrashCount = 0
$SupervisorLastSoundAt = $null
$SupervisorAlertsSilencedUntilHealthy = $false
$SupervisorSilenceReason = ""

function Get-MinutesLabel {
    param([double]$Seconds)

    $Minutes = [int][Math]::Max(1, [Math]::Round($Seconds / 60.0))
    if ($Minutes -eq 1) {
        return "1 MIN"
    }
    return ("{0} MINS" -f $Minutes)
}

function Get-ExitCodeText {
    param($Process)

    if ($null -eq $Process) {
        return "unknown"
    }

    try {
        $Process.Refresh()
    } catch {
    }

    try {
        if (-not $Process.HasExited) {
            return "still-running"
        }
    } catch {
    }

    try {
        [void]$Process.WaitForExit(1000)
    } catch {
    }

    try {
        $Code = $Process.ExitCode
        if ($null -ne $Code -and -not [string]::IsNullOrWhiteSpace([string]$Code)) {
            return [string]$Code
        }
    } catch {
    }

    return "unknown (process handle did not expose an exit code)"
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

function Test-WatchdogHeartbeatFresh {
    if (-not (Test-Path $Heartbeat)) {
        return $false
    }

    try {
        $AgeSeconds = ((Get-Date) - (Get-Item $Heartbeat).LastWriteTime).TotalSeconds
        return $AgeSeconds -le $StaleSeconds
    } catch {
        return $false
    }
}

function Get-WatchdogHeartbeatAge {
    if (-not (Test-Path $Heartbeat)) {
        return $null
    }

    try {
        return ((Get-Date) - (Get-Item $Heartbeat).LastWriteTime).TotalSeconds
    } catch {
        return $null
    }
}

function Record-SupervisorAbnormal {
    param(
        [string]$Reason,
        [object]$ExitCode = $null
    )

    $Now = Get-EpochSeconds
    $Event = [ordered]@{
        epoch_seconds = $Now
        reason = $Reason
    }
    if ($null -ne $ExitCode) {
        $Event.exit_code = [string]$ExitCode
    }
    [void]$script:SupervisorEvents.Add($Event)
    $script:SupervisorHealthySince = $null
    if ($null -eq $script:SupervisorUnavailableSince) {
        $script:SupervisorUnavailableSince = $Now
    }
}

function Get-PrunedSupervisorEvents {
    param([double]$Now)

    $Cutoff = $Now - $CrashWindowSeconds
    $Kept = @($script:SupervisorEvents | Where-Object { [double]$_.epoch_seconds -ge $Cutoff })
    $script:SupervisorEvents = New-Object System.Collections.ArrayList
    foreach ($Event in $Kept) {
        [void]$script:SupervisorEvents.Add($Event)
    }
    return $Kept
}

function Update-SupervisorHealth {
    param([bool]$WatchdogAvailable)

    $Now = Get-EpochSeconds
    $Events = @(Get-PrunedSupervisorEvents -Now $Now)

    if ($WatchdogAvailable) {
        $script:SupervisorUnavailableSince = $null
        $script:SupervisorAlertsSilencedUntilHealthy = $false
        $script:SupervisorSilenceReason = ""
    } elseif ($null -eq $script:SupervisorUnavailableSince) {
        $script:SupervisorUnavailableSince = $Now
    }

    $DownSeconds = 0.0
    if ($null -ne $script:SupervisorUnavailableSince) {
        $DownSeconds = [Math]::Max(0.0, $Now - [double]$script:SupervisorUnavailableSince)
    }
    if ((-not $WatchdogAvailable) -and ($DownSeconds -ge $SleepSilenceSeconds) -and (-not $script:SupervisorAlertsSilencedUntilHealthy)) {
        Silence-SupervisorAlertsUntilHealthy -Reason "watchdog down over sleep threshold"
    }

    $CrashCount = @($Events).Count
    $RawReason = ""
    $RawTitle = ""
    if ($CrashCount -ge $CrashAlertCount) {
        $RawReason = "crash_loop"
        $RawTitle = "WATCHDOG CRASHED {0} TIMES IN {1}" -f $CrashCount, (Get-MinutesLabel -Seconds $CrashWindowSeconds)
    } elseif ($DownSeconds -ge $WatchdogDownAlertSeconds) {
        $RawReason = "monitor_down"
        $RawTitle = "WATCHDOG DOWN {0}m+" -f ([Math]::Max(1, [int]($DownSeconds / 60.0)))
    }

    $RawActive = -not [string]::IsNullOrWhiteSpace($RawReason)
    $Latched = $false
    if ($RawActive) {
        if ($null -eq $script:SupervisorUnhealthySince) {
            $script:SupervisorUnhealthySince = $Now
        }
        $script:SupervisorHealthySince = $null
        $script:SupervisorLatchedTitle = $RawTitle
        $script:SupervisorLatchedReason = $RawReason
        if ($RawReason -eq "crash_loop") {
            $script:SupervisorLatchedCrashCount = $CrashCount
        }
    } elseif ($null -ne $script:SupervisorUnhealthySince) {
        if ($WatchdogAvailable) {
            if ($null -eq $script:SupervisorHealthySince) {
                $script:SupervisorHealthySince = $Now
            }
            if (($Now - [double]$script:SupervisorHealthySince) -ge $HealthyClearSeconds) {
                $script:SupervisorUnhealthySince = $null
                $script:SupervisorHealthySince = $null
                $script:SupervisorLatchedTitle = ""
                $script:SupervisorLatchedReason = ""
                $script:SupervisorLatchedCrashCount = 0
            } else {
                $Latched = $true
            }
        } else {
            $script:SupervisorHealthySince = $null
            $Latched = $true
        }
    }

    $Active = $RawActive -or $Latched
    $Reason = $RawReason
    $Title = $RawTitle
    if ($Latched -and [string]::IsNullOrWhiteSpace($Title)) {
        $Reason = $script:SupervisorLatchedReason
        $Title = $script:SupervisorLatchedTitle
    }
    $DisplayCrashCount = $CrashCount
    if (($Reason -eq "crash_loop") -and ($RawReason -ne "crash_loop")) {
        $DisplayCrashCount = $script:SupervisorLatchedCrashCount
    }

    return [ordered]@{
        active = [bool]$Active
        subject = "WATCHDOG"
        soundable = [bool]$RawActive
        latched = [bool]$Latched
        reason = $Reason
        title = $Title
        crash_count_window = $CrashCount
        display_crash_count = $DisplayCrashCount
        crash_alert_count = $CrashAlertCount
        window_seconds = $CrashWindowSeconds
        monitor_down_seconds = [Math]::Round($DownSeconds, 1)
        monitor_down_alert_seconds = $WatchdogDownAlertSeconds
        unhealthy_since = $script:SupervisorUnhealthySince
        healthy_since = $script:SupervisorHealthySince
        alerts_silenced_until_healthy = [bool]$script:SupervisorAlertsSilencedUntilHealthy
        silence_reason = $script:SupervisorSilenceReason
        recent_events = @($Events | Select-Object -Last 5)
    }
}

function Silence-SupervisorAlertsUntilHealthy {
    param([string]$Reason)

    $script:SupervisorAlertsSilencedUntilHealthy = $true
    $script:SupervisorSilenceReason = $Reason
}

function Write-SupervisorHeartbeat {
    param(
        $Watchdog,
        [int]$RestartCount,
        [string]$Status,
        [object]$Health
    )

    try {
        $ChildPid = $null
        if ($null -ne $Watchdog) {
            try {
                $ChildPid = $Watchdog.Id
            } catch {
                $ChildPid = $null
            }
        }

        $ParentDir = Split-Path -Parent $SupervisorHeartbeat
        if (-not (Test-Path $ParentDir)) {
            New-Item -ItemType Directory -Path $ParentDir -Force | Out-Null
        }

        $Payload = [ordered]@{
            time = (Get-Date).ToString("s")
            epoch_seconds = Get-EpochSeconds
            pid = $PID
            child_pid = $ChildPid
            restart_count = $RestartCount
            status = $Status
            watchdog_health = $Health
        }
        $TempPath = "$SupervisorHeartbeat.tmp"
        $Payload | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $TempPath -Encoding UTF8
        Move-Item -LiteralPath $TempPath -Destination $SupervisorHeartbeat -Force
    } catch {
        return
    }
}

function Test-SupervisorShouldSound {
    param([object]$Health)

    if (-not [bool]$Health.active) {
        return $false
    }
    if (-not [bool]$Health.soundable) {
        return $false
    }
    if ([bool]$Health.alerts_silenced_until_healthy) {
        return $false
    }

    $Now = Get-EpochSeconds
    if ($null -eq $script:SupervisorLastSoundAt) {
        return $true
    }
    return (($Now - [double]$script:SupervisorLastSoundAt) -ge $WatchdogRealertSeconds)
}

function Invoke-SupervisorHealthAlarm {
    param(
        [object]$Health,
        [string]$Message
    )

    if (-not (Test-SupervisorShouldSound -Health $Health)) {
        return $false
    }

    $Title = [string]$Health.title
    if (-not [string]::IsNullOrWhiteSpace($Title)) {
        $Message = "$Message; $Title"
    }
    Write-TimestampedHost ("Maple Alert supervisor: {0}" -f $Message) "Red"
    Invoke-SupervisorBeep
    $script:SupervisorLastSoundAt = Get-EpochSeconds
    if ([string]$Health.reason -eq "crash_loop") {
        $script:SupervisorEvents = New-Object System.Collections.ArrayList
    }
    return $true
}

function Get-SuppressedAlarmDetail {
    param([object]$Health)

    return (
        "audible alarm suppressed ({0}/{1} watchdog failures in {2}; watchdog_down={3}s)" -f
        $Health.crash_count_window,
        $Health.crash_alert_count,
        (Get-MinutesLabel -Seconds ([double]$Health.window_seconds)).ToLower(),
        $Health.monitor_down_seconds
    )
}

function Get-LogTailSummary {
    param(
        [string]$Path,
        [int]$MaxLines = 8
    )

    if (-not (Test-Path $Path)) {
        return ""
    }

    try {
        $Lines = @(Get-Content -LiteralPath $Path -Tail $MaxLines -ErrorAction Stop |
            Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) })
        if (@($Lines).Count -eq 0) {
            return ""
        }
        return ($Lines -join " | ")
    } catch {
        return ""
    }
}

function Write-WatchdogFailureDiagnostics {
    $StdErrTail = Get-LogTailSummary -Path $StdErr
    if (-not [string]::IsNullOrWhiteSpace($StdErrTail)) {
        Write-TimestampedHost ("Recent watchdog stderr: {0}" -f $StdErrTail) "DarkYellow"
    }
}

function Preserve-RestartLog {
    param(
        [string]$Path,
        [string]$Prefix,
        [int]$RestartCount
    )

    if (-not (Test-Path $Path)) {
        return
    }

    try {
        $Stamp = (Get-Date).ToString("yyyyMMdd_HHmmss_fff")
        $Destination = Join-Path $LogDir ("{0}_{1:D4}_{2}.log" -f $Prefix, $RestartCount, $Stamp)
        Move-Item -LiteralPath $Path -Destination $Destination -Force
        Get-ChildItem -LiteralPath $LogDir -Filter ("{0}_*.log" -f $Prefix) -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending |
            Select-Object -Skip 10 |
            Remove-Item -Force -ErrorAction SilentlyContinue
    } catch {
        Remove-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    }
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
            if ($Line -match "Maple alert:|Maple detection:|cleared|Quit request|Resolution|Detected new resolution|Maple|monitor exited|monitor heartbeat|monitor has not") {
                Write-ForwardedLine $Line
            }
        }
    } catch {
        return
    }
}

function Start-WatchdogProcess {
    param([int]$RestartCount = 0)

    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    Preserve-RestartLog -Path $StdOut -Prefix "watchdog_stdout" -RestartCount $RestartCount
    Preserve-RestartLog -Path $StdErr -Prefix "watchdog_stderr" -RestartCount $RestartCount

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
                Write-TimestampedHost ("Started heartbeat overlay pid={0}" -f $Overlay.Id)
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
            Write-TimestampedHost ("Maple not detected; using monitor fallback at resolution {0}x{1}." -f $Width, $Height) "Red"
            return
        }

        if ($TargetWindow -and $MapleDetected -and ($PreviousKey -eq "" -or $PreviousKey -match "\|False$")) {
            Write-TimestampedHost ("Maple detected; using window capture at resolution {0}x{1}." -f $Width, $Height) "Green"
            return
        }

        Write-TimestampedHost ("Detected new resolution {0}x{1}; capture source={2}." -f $Width, $Height, $Source) "Cyan"
    } catch {
        return
    }
}

Write-TimestampedHost "Maple Alert outer supervisor is running."
Write-TimestampedHost "It will restart the watchdog if the watchdog exits or stops updating $Heartbeat."
Write-TimestampedHost "Watchdog audio stays quiet until the configured unhealthy thresholds are crossed."
Write-TimestampedHost "Close this window to stop monitoring."
Write-Host ""
Remove-Item -LiteralPath $QuitRequest -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $SupervisorHeartbeat -Force -ErrorAction SilentlyContinue

$RestartCount = 0
$Overlay = $null
$Watchdog = $null
$QuitRequested = $false
$InitialHealth = Update-SupervisorHealth -WatchdogAvailable $false
Write-SupervisorHeartbeat -Watchdog $null -RestartCount $RestartCount -Status "starting" -Health $InitialHealth

try {
    while (-not $QuitRequested) {
        Remove-Item -LiteralPath $Heartbeat -Force -ErrorAction SilentlyContinue

        $Overlay = Update-OverlayProcess -Overlay $Overlay
        try {
            $Watchdog = Start-WatchdogProcess -RestartCount $RestartCount
        } catch {
            $RestartCount += 1
            Record-SupervisorAbnormal -Reason "watchdog_start_failed" -ExitCode "start_failed"
            $Health = Update-SupervisorHealth -WatchdogAvailable $false
            Write-SupervisorHeartbeat -Watchdog $null -RestartCount $RestartCount -Status "watchdog_start_failed" -Health $Health
            $Message = "watchdog could not start: {0}; retrying in {1}s (supervisor restart #{2} since launch)" -f $_.Exception.Message, $RestartDelaySeconds, $RestartCount
            if (-not (Invoke-SupervisorHealthAlarm -Health $Health -Message $Message)) {
                Write-TimestampedHost ("{0}; {1}" -f $Message, (Get-SuppressedAlarmDetail -Health $Health)) "Yellow"
            }
            Start-Sleep -Seconds $RestartDelaySeconds
            continue
        }

        $script:LastStdOutPosition = 0
        $StartedAt = Get-Date
        $LastSupervisorCheck = Get-Date
        $Health = Update-SupervisorHealth -WatchdogAvailable $false
        Write-SupervisorHeartbeat -Watchdog $Watchdog -RestartCount $RestartCount -Status "watchdog_started" -Health $Health
        Write-TimestampedHost ("Started watchdog pid={0}" -f $Watchdog.Id)

        while ($true) {
            Start-Sleep -Seconds $CheckIntervalSeconds
            $NowCheck = Get-Date
            $CheckGapSeconds = ($NowCheck - $LastSupervisorCheck).TotalSeconds
            if ($CheckGapSeconds -gt $SleepSilenceSeconds) {
                if (-not $script:SupervisorAlertsSilencedUntilHealthy) {
                    Silence-SupervisorAlertsUntilHealthy -Reason "long sleep or wake gap"
                    Write-TimestampedHost ("Long sleep/wake gap detected ({0:N1}s); watchdog audio is silenced until heartbeat recovers." -f $CheckGapSeconds) "Yellow"
                }
            }
            $LastSupervisorCheck = $NowCheck
            Write-NewWatchdogOutput
            if (Test-QuitRequested) {
                $QuitRequested = $true
                Write-TimestampedHost "Quit requested from overlay. Stopping Maple Alert..."
                break
            }

            $Overlay = Update-OverlayProcess -Overlay $Overlay
            Write-MonitorStatusChanges

            try {
                $Watchdog.Refresh()
            } catch {
            }

            $WatchdogFresh = $false
            if ($null -ne $Watchdog -and -not $Watchdog.HasExited) {
                $WatchdogFresh = Test-WatchdogHeartbeatFresh
            }
            $Health = Update-SupervisorHealth -WatchdogAvailable $WatchdogFresh
            Write-SupervisorHeartbeat -Watchdog $Watchdog -RestartCount $RestartCount -Status "watching" -Health $Health
            [void](Invoke-SupervisorHealthAlarm -Health $Health -Message "watchdog health is degraded")

            if ($Watchdog.HasExited) {
                $RestartCount += 1
                $ExitCodeText = Get-ExitCodeText -Process $Watchdog
                Record-SupervisorAbnormal -Reason "watchdog_exited" -ExitCode $ExitCodeText
                $Health = Update-SupervisorHealth -WatchdogAvailable $false
                Write-SupervisorHeartbeat -Watchdog $Watchdog -RestartCount $RestartCount -Status "watchdog_exited" -Health $Health
                Write-WatchdogFailureDiagnostics
                $Message = "watchdog exited with code {0}; restarting in {1}s (supervisor restart #{2} since launch)" -f $ExitCodeText, $RestartDelaySeconds, $RestartCount
                if (-not (Invoke-SupervisorHealthAlarm -Health $Health -Message $Message)) {
                    Write-TimestampedHost ("{0}; {1}" -f $Message, (Get-SuppressedAlarmDetail -Health $Health)) "Yellow"
                }
                break
            }

            $AgeSeconds = Get-WatchdogHeartbeatAge
            if ($null -ne $AgeSeconds) {
                if ($AgeSeconds -gt $StaleSeconds) {
                    if (($AgeSeconds -gt $SleepSilenceSeconds) -and (-not $script:SupervisorAlertsSilencedUntilHealthy)) {
                        Silence-SupervisorAlertsUntilHealthy -Reason "watchdog heartbeat stale over sleep threshold"
                        Write-TimestampedHost ("Watchdog heartbeat is stale over sleep threshold ({0:N1}s old); watchdog audio is silenced until heartbeat recovers." -f $AgeSeconds) "Yellow"
                    }
                    $RestartCount += 1
                    Record-SupervisorAbnormal -Reason "watchdog_stale"
                    $Health = Update-SupervisorHealth -WatchdogAvailable $false
                    Write-SupervisorHeartbeat -Watchdog $Watchdog -RestartCount $RestartCount -Status "watchdog_stale" -Health $Health
                    Write-WatchdogFailureDiagnostics
                    $Message = "watchdog heartbeat is stale ({0:N1}s old); restarting in {1}s (supervisor restart #{2} since launch)" -f $AgeSeconds, $RestartDelaySeconds, $RestartCount
                    if (-not (Invoke-SupervisorHealthAlarm -Health $Health -Message $Message)) {
                        Write-TimestampedHost ("{0}; {1}" -f $Message, (Get-SuppressedAlarmDetail -Health $Health)) "Yellow"
                    }
                    Stop-ProcessTree -ProcessId $Watchdog.Id
                    break
                }
            } elseif (((Get-Date) - $StartedAt).TotalSeconds -gt $StartupGraceSeconds) {
                $RestartCount += 1
                Record-SupervisorAbnormal -Reason "watchdog_missing_heartbeat"
                $Health = Update-SupervisorHealth -WatchdogAvailable $false
                Write-SupervisorHeartbeat -Watchdog $Watchdog -RestartCount $RestartCount -Status "watchdog_missing_heartbeat" -Health $Health
                Write-WatchdogFailureDiagnostics
                $Message = "watchdog did not write a heartbeat after {0}s; restarting in {1}s (supervisor restart #{2} since launch)" -f $StartupGraceSeconds, $RestartDelaySeconds, $RestartCount
                if (-not (Invoke-SupervisorHealthAlarm -Health $Health -Message $Message)) {
                    Write-TimestampedHost ("{0}; {1}" -f $Message, (Get-SuppressedAlarmDetail -Health $Health)) "Yellow"
                }
                Stop-ProcessTree -ProcessId $Watchdog.Id
                break
            }
        }

        if ($QuitRequested) {
            break
        }
        $Health = Update-SupervisorHealth -WatchdogAvailable $false
        Write-SupervisorHeartbeat -Watchdog $null -RestartCount $RestartCount -Status "restarting" -Health $Health
        Start-Sleep -Seconds $RestartDelaySeconds
    }
}
finally {
    Write-TimestampedHost "Stopping Maple Alert child processes..."
    if ($null -ne $Overlay -and -not $Overlay.HasExited) {
        Stop-ProcessTree -ProcessId $Overlay.Id
    }
    if ($null -ne $Watchdog -and -not $Watchdog.HasExited) {
        Stop-ProcessTree -ProcessId $Watchdog.Id
    }
}
