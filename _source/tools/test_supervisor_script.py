from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "watchdog_supervisor.ps1"


def powershell_literal(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def test_supervisor_script_uses_clear_watchdog_restart_wording() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "supervisor restart #{2} since launch" in text
    assert "watchdog failures in" in text


def test_supervisor_script_uses_five_crash_threshold_and_resets_after_alert() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert 'crash_alert_count" -Default 5.0' in text
    assert "$script:SupervisorEvents = New-Object System.Collections.ArrayList" in text
    assert "$SupervisorLatchedCrashCount = 0" in text
    assert "display_crash_count = $DisplayCrashCount" in text
    assert "$WatchdogRealertSeconds = [Math]::Max(60.0" in text


def test_supervisor_script_silences_alerts_after_long_sleep_gap() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert 'sleep_silence_seconds" -Default 3600.0' in text
    assert "Silence-SupervisorAlertsUntilHealthy" in text
    assert "SupervisorAlertsSilencedUntilHealthy" in text
    assert "Long sleep/wake gap detected" in text
    assert "Watchdog heartbeat is stale over sleep threshold" in text
    assert "watchdog down over sleep threshold" in text
    assert "$DownSeconds -ge $SleepSilenceSeconds" in text


def test_supervisor_script_preserves_failure_diagnostics() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "function Preserve-RestartLog" in text
    assert "Recent watchdog stderr" in text
    assert "unknown (process handle did not expose an exit code)" in text


def test_supervisor_script_parses_as_powershell() -> None:
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        return

    script_path = powershell_literal(SCRIPT)
    command = (
        "$tokens = $null; $errors = $null; "
        f"[System.Management.Automation.Language.Parser]::ParseFile({script_path}, [ref]$tokens, [ref]$errors) | Out-Null; "
        "if ($errors.Count -gt 0) { "
        "$errors | ForEach-Object { Write-Error $_.Message }; exit 1 "
        "}"
    )
    completed = subprocess.run(
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        check=False,
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


if __name__ == "__main__":
    test_supervisor_script_uses_clear_watchdog_restart_wording()
    test_supervisor_script_uses_five_crash_threshold_and_resets_after_alert()
    test_supervisor_script_silences_alerts_after_long_sleep_gap()
    test_supervisor_script_preserves_failure_diagnostics()
    test_supervisor_script_parses_as_powershell()
    print("supervisor script tests passed")
