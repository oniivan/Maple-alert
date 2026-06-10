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
    config["watchdog"]["crash_alert_count"] = 5
    config["watchdog"]["monitor_down_alert_seconds"] = 120
    config["watchdog"]["watchdog_realert_seconds"] = 120
    config["watchdog"]["healthy_clear_seconds"] = 600
    config["watchdog"]["sleep_silence_seconds"] = 3600
    return config


def test_single_monitor_exit_restarts_quietly() -> None:
    tracker = WatchdogFailureTracker(make_config())

    tracker.record_abnormal("monitor_exited", now=10.0, exit_code=1)
    snapshot = tracker.update(monitor_available=False, now=10.0)

    assert snapshot["active"] is False
    assert snapshot["crash_count_window"] == 1
    assert tracker.should_sound(snapshot, now=10.0) is False


def test_four_monitor_exits_restart_quietly() -> None:
    tracker = WatchdogFailureTracker(make_config())

    for timestamp in (10.0, 20.0, 30.0, 40.0):
        tracker.record_abnormal("monitor_exited", now=timestamp, exit_code=1)
    snapshot = tracker.update(monitor_available=False, now=40.0)

    assert snapshot["active"] is False
    assert snapshot["crash_count_window"] == 4
    assert tracker.should_sound(snapshot, now=40.0) is False


def test_five_crashes_sound_once_and_reset_crash_counter() -> None:
    tracker = WatchdogFailureTracker(make_config())

    for timestamp in (10.0, 40.0, 70.0, 100.0, 130.0):
        tracker.record_abnormal("monitor_exited", now=timestamp, exit_code=1)
    snapshot = tracker.update(monitor_available=False, now=130.0)

    assert snapshot["active"] is True
    assert snapshot["reason"] == "crash_loop"
    assert snapshot["title"] == "MONITOR CRASHED 5 TIMES IN 5 MINS"
    assert (
        overlay_watchdog_health_text(snapshot, "|", now_epoch=132.0)
        == "ERROR: MAPLEALERT CRASHED 5 TIMES |"
    )
    assert (
        overlay_watchdog_health_text(snapshot, "|", now_epoch=135.0)
        == "SEE ERROR IN TERMINAL |"
    )
    assert tracker.should_sound(snapshot, now=130.0) is True

    tracker.mark_sounded(snapshot, now=130.0)
    recovered = tracker.update(monitor_available=True, now=131.0)
    assert recovered["crash_count_window"] == 0
    assert recovered["display_crash_count"] == 5
    assert (
        overlay_watchdog_health_text(recovered, "|", now_epoch=132.0)
        == "ERROR: MAPLEALERT CRASHED 5 TIMES |"
    )
    assert tracker.should_sound(recovered, now=251.0) is False


def test_second_crash_loop_needs_five_new_crashes() -> None:
    config = make_config()
    config["watchdog"]["watchdog_realert_seconds"] = 60
    tracker = WatchdogFailureTracker(config)

    for timestamp in (0.0, 10.0, 20.0, 30.0, 40.0):
        tracker.record_abnormal("monitor_exited", now=timestamp, exit_code=1)
    snapshot = tracker.update(monitor_available=False, now=40.0)
    assert tracker.should_sound(snapshot, now=40.0) is True
    tracker.mark_sounded(snapshot, now=40.0)
    tracker.update(monitor_available=True, now=41.0)

    for timestamp in (50.0, 60.0, 70.0, 80.0):
        tracker.record_abnormal("monitor_exited", now=timestamp, exit_code=1)
    snapshot = tracker.update(monitor_available=False, now=100.0)
    assert snapshot["crash_count_window"] == 4
    assert snapshot["display_crash_count"] == 5
    assert tracker.should_sound(snapshot, now=100.0) is False

    tracker.record_abnormal("monitor_exited", now=101.0, exit_code=1)
    snapshot = tracker.update(monitor_available=False, now=101.0)
    assert snapshot["crash_count_window"] == 5
    assert snapshot["display_crash_count"] == 5
    assert tracker.should_sound(snapshot, now=101.0) is True


def test_watchdog_subject_uses_watchdog_title() -> None:
    tracker = WatchdogFailureTracker(make_config(), subject="WATCHDOG")

    for timestamp in (10.0, 70.0, 130.0):
        tracker.record_abnormal("watchdog_exited", now=timestamp, exit_code=1)
    for timestamp in (160.0, 190.0):
        tracker.record_abnormal("watchdog_exited", now=timestamp, exit_code=1)
    snapshot = tracker.update(monitor_available=False, now=190.0)

    assert snapshot["subject"] == "WATCHDOG"
    assert snapshot["title"] == "WATCHDOG CRASHED 5 TIMES IN 5 MINS"
    assert (
        overlay_watchdog_health_text(snapshot, "|", now_epoch=132.0)
        == "ERROR: MAPLEALERT CRASHED 5 TIMES |"
    )


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


def test_watchdog_realert_floor_is_sixty_seconds() -> None:
    config = make_config()
    config["watchdog"]["watchdog_realert_seconds"] = 5
    tracker = WatchdogFailureTracker(config)

    for timestamp in (0.0, 10.0, 20.0):
        tracker.record_abnormal("monitor_exited", now=timestamp, exit_code=1)
    for timestamp in (30.0, 40.0):
        tracker.record_abnormal("monitor_exited", now=timestamp, exit_code=1)
    snapshot = tracker.update(monitor_available=False, now=40.0)

    assert tracker.should_sound(snapshot, now=40.0) is True
    tracker.mark_sounded(snapshot, now=40.0)

    for timestamp in (50.0, 60.0, 70.0, 80.0, 90.0):
        tracker.record_abnormal("monitor_exited", now=timestamp, exit_code=1)
    snapshot = tracker.update(monitor_available=False, now=99.0)
    assert tracker.should_sound(snapshot, now=99.0) is False
    assert tracker.should_sound(snapshot, now=100.0) is True


def test_watchdog_remote_sends_once_per_unhealthy_instance() -> None:
    tracker = WatchdogFailureTracker(make_config())

    snapshot = tracker.update(monitor_available=False, now=0.0)
    assert not tracker.should_send_remote(snapshot)
    snapshot = tracker.update(monitor_available=False, now=120.0)
    assert tracker.should_send_remote(snapshot)
    tracker.mark_remote_sent()
    assert not tracker.should_send_remote(snapshot)

    snapshot = tracker.update(monitor_available=True, now=121.0)
    assert snapshot["active"] is True
    snapshot = tracker.update(monitor_available=True, now=721.0)
    assert snapshot["active"] is False
    snapshot = tracker.update(monitor_available=False, now=722.0)
    snapshot = tracker.update(monitor_available=False, now=842.0)
    assert tracker.should_send_remote(snapshot)


def test_watchdog_sleep_silence_suppresses_alerts_until_healthy() -> None:
    tracker = WatchdogFailureTracker(make_config())

    tracker.suppress_alerts_until_healthy("long sleep or wake gap")
    snapshot = tracker.update(monitor_available=False, now=4000.0)
    snapshot = tracker.update(monitor_available=False, now=4120.0)

    assert snapshot["active"] is True
    assert snapshot["alerts_silenced_until_healthy"] is True
    assert tracker.should_sound(snapshot, now=4120.0) is False
    assert tracker.should_send_remote(snapshot) is False

    recovered = tracker.update(monitor_available=True, now=4121.0)
    assert recovered["alerts_silenced_until_healthy"] is False


def test_watchdog_long_downtime_suppresses_alerts_until_healthy() -> None:
    tracker = WatchdogFailureTracker(make_config())

    snapshot = tracker.update(monitor_available=False, now=0.0)
    snapshot = tracker.update(monitor_available=False, now=120.0)
    assert snapshot["active"] is True
    assert tracker.should_sound(snapshot, now=120.0) is True

    snapshot = tracker.update(monitor_available=False, now=3600.0)
    assert snapshot["active"] is True
    assert snapshot["alerts_silenced_until_healthy"] is True
    assert tracker.should_sound(snapshot, now=3600.0) is False
    assert tracker.should_send_remote(snapshot) is False

    recovered = tracker.update(monitor_available=True, now=3601.0)
    assert recovered["alerts_silenced_until_healthy"] is False


def test_degraded_state_stays_latched_until_clean_recovery() -> None:
    tracker = WatchdogFailureTracker(make_config())

    for timestamp in (0.0, 30.0, 60.0, 90.0, 120.0):
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
    test_four_monitor_exits_restart_quietly()
    test_five_crashes_sound_once_and_reset_crash_counter()
    test_second_crash_loop_needs_five_new_crashes()
    test_watchdog_subject_uses_watchdog_title()
    test_sustained_monitor_downtime_triggers_even_without_many_crashes()
    test_watchdog_realert_floor_is_sixty_seconds()
    test_watchdog_remote_sends_once_per_unhealthy_instance()
    test_watchdog_sleep_silence_suppresses_alerts_until_healthy()
    test_watchdog_long_downtime_suppresses_alerts_until_healthy()
    test_degraded_state_stays_latched_until_clean_recovery()
    print("watchdog failure policy tests passed")
