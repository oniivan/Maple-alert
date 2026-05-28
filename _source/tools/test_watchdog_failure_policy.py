from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from maple_alert import (
    DEFAULT_CONFIG,
    WatchdogFailureTracker,
    overlay_watchdog_health_text,
)


def make_config() -> dict:
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["watchdog"]["crash_window_seconds"] = 300
    config["watchdog"]["crash_alert_count"] = 3
    config["watchdog"]["monitor_down_alert_seconds"] = 120
    config["watchdog"]["watchdog_realert_seconds"] = 120
    config["watchdog"]["healthy_clear_seconds"] = 600
    return config


def test_single_monitor_exit_restarts_quietly() -> None:
    tracker = WatchdogFailureTracker(make_config())

    tracker.record_abnormal("monitor_exited", now=10.0, exit_code=1)
    snapshot = tracker.update(monitor_available=False, now=10.0)

    assert snapshot["active"] is False
    assert snapshot["crash_count_window"] == 1
    assert tracker.should_sound(snapshot, now=10.0) is False


def test_crash_loop_sounds_once_then_realerts_after_interval() -> None:
    tracker = WatchdogFailureTracker(make_config())

    for timestamp in (10.0, 70.0, 130.0):
        tracker.record_abnormal("monitor_exited", now=timestamp, exit_code=1)
    snapshot = tracker.update(monitor_available=False, now=130.0)

    assert snapshot["active"] is True
    assert snapshot["reason"] == "crash_loop"
    assert snapshot["title"] == "MONITOR CRASHED 3 TIMES IN 5 MINS"
    assert overlay_watchdog_health_text(snapshot, "|") == "MONITOR CRASHED 3 TIMES IN 5 MINS |"
    assert tracker.should_sound(snapshot, now=130.0) is True

    tracker.mark_sounded(now=130.0)
    assert tracker.should_sound(snapshot, now=200.0) is False
    assert tracker.should_sound(snapshot, now=251.0) is True


def test_watchdog_subject_uses_watchdog_title() -> None:
    tracker = WatchdogFailureTracker(make_config(), subject="WATCHDOG")

    for timestamp in (10.0, 70.0, 130.0):
        tracker.record_abnormal("watchdog_exited", now=timestamp, exit_code=1)
    snapshot = tracker.update(monitor_available=False, now=130.0)

    assert snapshot["subject"] == "WATCHDOG"
    assert snapshot["title"] == "WATCHDOG CRASHED 3 TIMES IN 5 MINS"
    assert overlay_watchdog_health_text(snapshot, "|") == "WATCHDOG CRASHED 3 TIMES IN 5 MINS |"


def test_sustained_monitor_downtime_triggers_even_without_many_crashes() -> None:
    tracker = WatchdogFailureTracker(make_config())

    snapshot = tracker.update(monitor_available=False, now=0.0)
    assert snapshot["active"] is False

    snapshot = tracker.update(monitor_available=False, now=119.0)
    assert snapshot["active"] is False

    snapshot = tracker.update(monitor_available=False, now=120.0)
    assert snapshot["active"] is True
    assert snapshot["reason"] == "monitor_down"
    assert snapshot["title"] == "MONITOR DOWN 2m+"
    assert tracker.should_sound(snapshot, now=120.0) is True


def test_degraded_state_stays_latched_until_clean_recovery() -> None:
    tracker = WatchdogFailureTracker(make_config())

    for timestamp in (0.0, 60.0, 120.0):
        tracker.record_abnormal("monitor_exited", now=timestamp, exit_code=1)
    snapshot = tracker.update(monitor_available=False, now=120.0)
    assert snapshot["active"] is True

    snapshot = tracker.update(monitor_available=True, now=301.0)
    assert snapshot["active"] is True
    assert snapshot["latched"] is True

    snapshot = tracker.update(monitor_available=True, now=900.0)
    assert snapshot["active"] is True

    snapshot = tracker.update(monitor_available=True, now=901.0)
    assert snapshot["active"] is False
    assert snapshot["title"] == ""


if __name__ == "__main__":
    test_single_monitor_exit_restarts_quietly()
    test_crash_loop_sounds_once_then_realerts_after_interval()
    test_watchdog_subject_uses_watchdog_title()
    test_sustained_monitor_downtime_triggers_even_without_many_crashes()
    test_degraded_state_stays_latched_until_clean_recovery()
    print("watchdog failure policy tests passed")
