from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from maple_alert import AlertManager, DetectionResult, format_last_seen_minutes, overlay_live_status_text


def make_config(config_dir: str, required_seconds: float = 20.0) -> dict:
    return {
        "_config_dir": config_dir,
        "alerts": {
            "audible": False,
            "safe_mode": True,
            "telegram_enabled": False,
            "captcha_repeat_seconds": 30,
            "minimap_required_seconds": required_seconds,
            "minimap_repeat_seconds": 30,
            "detection_log_interval_seconds": 0,
            "alert_settings_file": "runtime/test_alert_settings.json",
        },
        "telegram": {"bot_token": "", "chat_id": ""},
    }


def test_lie_last_seen_persists_after_clear() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        manager = AlertManager(make_config(temp_dir), logging.getLogger("test_lie_status"))

        manager.handle_result("captcha", DetectionResult(True, 0.95, {}))
        active = manager.status_snapshot()
        assert active["lie_last_seen_epoch"] is not None
        assert active["active_alert"] == "lie_detector"

        manager.handle_result("captcha", DetectionResult(False, 0.0, {}))
        cleared = manager.status_snapshot()
        assert cleared["lie_last_seen_epoch"] == active["lie_last_seen_epoch"]
        assert cleared["active_alert"] is None


def test_player_last_seen_waits_for_actual_alert_threshold() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        manager = AlertManager(
            make_config(temp_dir, required_seconds=999),
            logging.getLogger("test_player_status"),
        )

        manager.handle_result("minimap_red", DetectionResult(True, 1.0, {"red_pixels": 60}))
        snapshot = manager.status_snapshot()

        assert snapshot["player_last_seen_epoch"] is None
        assert snapshot["active_alert"] is None


def test_player_last_seen_updates_when_player_alert_fires() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        manager = AlertManager(
            make_config(temp_dir, required_seconds=0),
            logging.getLogger("test_player_alert_status"),
        )

        manager.handle_result("minimap_red", DetectionResult(True, 1.0, {"red_pixels": 60}))
        snapshot = manager.status_snapshot()

        assert snapshot["player_last_seen_epoch"] is not None
        assert snapshot["active_alert"] == "player_detected"


def test_last_seen_minutes_format() -> None:
    assert format_last_seen_minutes(None, now_epoch=1000.0) == "CLEAR"
    assert format_last_seen_minutes(995.0, now_epoch=1000.0) == "0m ago"
    assert format_last_seen_minutes(880.0, now_epoch=1000.0) == "2m ago"


def test_overlay_live_status_only_shows_seen_signals() -> None:
    assert overlay_live_status_text({}, "|", now_epoch=1000.0) == "LIVE |"
    assert (
        overlay_live_status_text({"lie_last_seen_epoch": 940.0}, "|", now_epoch=1000.0)
        == "LIVE | LIE 1m ago |"
    )
    assert (
        overlay_live_status_text({"player_last_seen_epoch": 820.0}, "/", now_epoch=1000.0)
        == "LIVE | PLAYER 3m ago /"
    )
    assert (
        overlay_live_status_text(
            {"lie_last_seen_epoch": 995.0, "player_last_seen_epoch": 880.0},
            "-",
            now_epoch=1000.0,
        )
        == "LIVE | LIE 0m ago PLAYER 2m ago -"
    )


if __name__ == "__main__":
    test_lie_last_seen_persists_after_clear()
    test_player_last_seen_waits_for_actual_alert_threshold()
    test_player_last_seen_updates_when_player_alert_fires()
    test_last_seen_minutes_format()
    test_overlay_live_status_only_shows_seen_signals()
    print("alert status payload tests passed")
