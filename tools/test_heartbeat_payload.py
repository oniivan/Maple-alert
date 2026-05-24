from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from maple_alert import Rect, write_heartbeat


def test_heartbeat_marks_window_missing_when_monitor_fallback_is_used() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        config = {
            "_config_dir": temp_dir,
            "capture": {"target_window": True, "window_title": "MapleStory Worlds"},
            "watchdog": {"heartbeat_file": "runtime/heartbeat.json"},
            "_runtime_scale": {"pixel_scale": 1.0},
        }

        write_heartbeat(config, "monitor", Rect(0, 0, 1920, 1080))
        payload = json.loads((Path(temp_dir) / "runtime" / "heartbeat.json").read_text())

        assert payload["target_window"] is True
        assert payload["maplestory_detected"] is False
        assert payload["source"] == "monitor"
        assert payload["resolution"] == [1920, 1080]


def test_heartbeat_marks_window_detected_when_window_capture_is_used() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        config = {
            "_config_dir": temp_dir,
            "capture": {"target_window": True, "window_title": "MapleStory Worlds"},
            "watchdog": {"heartbeat_file": "runtime/heartbeat.json"},
            "_runtime_scale": {"pixel_scale": 1.0},
        }

        write_heartbeat(config, "window", Rect(50, 50, 1600, 900))
        payload = json.loads((Path(temp_dir) / "runtime" / "heartbeat.json").read_text())

        assert payload["maplestory_detected"] is True
        assert payload["source"] == "window"
        assert payload["resolution"] == [1600, 900]


if __name__ == "__main__":
    test_heartbeat_marks_window_missing_when_monitor_fallback_is_used()
    test_heartbeat_marks_window_detected_when_window_capture_is_used()
    print("heartbeat payload tests passed")
