from __future__ import annotations

import json
import logging
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
            "title": "MONITOR CRASHED 5 TIMES IN 5 MINS",
            "crash_count_window": 5,
            "display_crash_count": 5,
        }
        write_watchdog_heartbeat(config, child_pid=123, restart_count=3, status="monitor_exited", monitor_health=health)
        payload = json.loads((Path(temp_dir) / "runtime" / "watchdog_heartbeat.json").read_text())

        assert payload["monitor_health"] == health
        assert payload["status"] == "monitor_exited"


def test_watchdog_heartbeat_retries_transient_replace_denial() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        config = {
            "_config_dir": temp_dir,
            "watchdog": {"watchdog_heartbeat_file": "runtime/watchdog_heartbeat.json"},
        }
        path_type = type(Path(temp_dir) / "runtime" / "watchdog_heartbeat.json")
        real_replace = path_type.replace
        calls = {"denied": 0}

        def flaky_replace(self: Path, target: Path) -> Path:
            if self.name.startswith("watchdog_heartbeat.json") and self.name.endswith(".tmp") and calls["denied"] == 0:
                calls["denied"] += 1
                raise PermissionError(5, "Access is denied", str(target))
            return real_replace(self, target)

        path_type.replace = flaky_replace
        try:
            write_watchdog_heartbeat(config, child_pid=456, restart_count=2, status="watching")
        finally:
            path_type.replace = real_replace

        payload = json.loads((Path(temp_dir) / "runtime" / "watchdog_heartbeat.json").read_text())
        assert calls["denied"] == 1
        assert payload["child_pid"] == 456
        assert payload["status"] == "watching"


def test_watchdog_heartbeat_persistent_replace_denial_is_nonfatal() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        config = {
            "_config_dir": temp_dir,
            "watchdog": {"watchdog_heartbeat_file": "runtime/watchdog_heartbeat.json"},
        }
        path_type = type(Path(temp_dir) / "runtime" / "watchdog_heartbeat.json")
        real_replace = path_type.replace
        logger = logging.getLogger("maple_alert")
        logger_disabled = logger.disabled

        def locked_replace(self: Path, target: Path) -> Path:
            if self.name.startswith("watchdog_heartbeat.json") and self.name.endswith(".tmp"):
                raise PermissionError(5, "Access is denied", str(target))
            return real_replace(self, target)

        path_type.replace = locked_replace
        logger.disabled = True
        try:
            write_watchdog_heartbeat(config, child_pid=789, restart_count=4, status="watching")
        finally:
            logger.disabled = logger_disabled
            path_type.replace = real_replace

        assert not (Path(temp_dir) / "runtime" / "watchdog_heartbeat.json").exists()


if __name__ == "__main__":
    test_heartbeat_marks_window_missing_when_monitor_fallback_is_used()
    test_heartbeat_marks_window_detected_when_window_capture_is_used()
    test_watchdog_heartbeat_includes_monitor_health()
    test_watchdog_heartbeat_retries_transient_replace_denial()
    test_watchdog_heartbeat_persistent_replace_denial_is_nonfatal()
    print("heartbeat payload tests passed")
