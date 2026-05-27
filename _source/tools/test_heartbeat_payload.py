from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from maple_alert import Rect, write_heartbeat, write_watchdog_heartbeat


def test_heartbeat_marks_window_missing_when_monitor_fallback_is_used() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        config = {
            "_config_dir": temp_dir,
            "capture": {"target_window": True, "window_title": "Maple"},
            "watchdog": {"heartbeat_file": "runtime/heartbeat.json"},
            "_runtime_scale": {"pixel_scale": 1.0},
        }

        write_heartbeat(config, "monitor", Rect(0, 0, 1920, 1080))
        payload = json.loads((Path(temp_dir) / "runtime" / "heartbeat.json").read_text())

        assert payload["target_window"] is True
        assert payload["maple_detected"] is False
        assert payload["source"] == "monitor"
        assert payload["resolution"] == [1920, 1080]


def test_heartbeat_marks_window_detected_when_window_capture_is_used() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        config = {
            "_config_dir": temp_dir,
            "capture": {"target_window": True, "window_title": "Maple"},
            "watchdog": {"heartbeat_file": "runtime/heartbeat.json"},
            "_runtime_scale": {"pixel_scale": 1.0},
        }

        write_heartbeat(config, "window", Rect(50, 50, 1600, 900))
        payload = json.loads((Path(temp_dir) / "runtime" / "heartbeat.json").read_text())

        assert payload["maple_detected"] is True
        assert payload["source"] == "window"
        assert payload["resolution"] == [1600, 900]


def test_watchdog_heartbeat_includes_monitor_health() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        config = {
            "_config_dir": temp_dir,
            "watchdog": {"watchdog_heartbeat_file": "runtime/watchdog_heartbeat.json"},
        }

        health = {
            "active": True,
            "title": "MONITOR CRASHED 3 TIMES IN 5 MINS",
            "crash_count_window": 3,
        }
        write_watchdog_heartbeat(config, child_pid=123, restart_count=3, status="monitor_exited", monitor_health=health)
        payload = json.loads((Path(temp_dir) / "runtime" / "watchdog_heartbeat.json").read_text())

        assert payload["monitor_health"] == health
        assert payload["status"] == "monitor_exited"


if __name__ == "__main__":
    test_heartbeat_marks_window_missing_when_monitor_fallback_is_used()
    test_heartbeat_marks_window_detected_when_window_capture_is_used()
    test_watchdog_heartbeat_includes_monitor_health()
    print("heartbeat payload tests passed")
