from __future__ import annotations

import io
import logging
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import maple_alert
from maple_alert import AlertManager, DetectionResult


def make_config() -> dict:
    return {
        "_config_dir": str(Path.cwd()),
        "alerts": {
            "audible": False,
            "safe_mode": True,
            "telegram_enabled": False,
            "captcha_repeat_seconds": 30,
            "dead_player_repeat_seconds": 30,
            "minimap_required_seconds": 0,
            "minimap_repeat_seconds": 30,
            "detection_log_interval_seconds": 0,
            "alert_settings_file": "runtime/test_alert_settings.json",
        },
        "telegram": {"bot_token": "", "chat_id": ""},
    }


def test_captcha_prints_alert_and_clear() -> None:
    manager = AlertManager(make_config(), logging.getLogger("test_captcha_prints"))
    out = io.StringIO()
    with redirect_stdout(out):
        manager.handle_result("captcha", DetectionResult(True, 0.91, {}))
        manager.handle_result("captcha", DetectionResult(False, 0.0, {}))

    text = out.getvalue()
    assert "Maple alert: CAPTCHA/lie detector" in text
    assert "Maple detection: CAPTCHA/lie detector cleared." in text


def test_minimap_prints_detected_alert_and_clear() -> None:
    manager = AlertManager(make_config(), logging.getLogger("test_minimap_prints"))
    out = io.StringIO()
    with redirect_stdout(out):
        manager.handle_result("minimap_red", DetectionResult(True, 0.9, {"red_pixels": 60}))
        manager.handle_result("minimap_red", DetectionResult(False, 0.0, {}))

    text = out.getvalue()
    assert "Maple detection: red minimap marker detected." in text
    assert "Maple alert: red minimap marker." in text
    assert "Maple detection: red minimap marker cleared." in text


def test_dead_player_prints_alert_and_clear() -> None:
    manager = AlertManager(make_config(), logging.getLogger("test_dead_player_prints"))
    out = io.StringIO()
    with redirect_stdout(out):
        manager.handle_result("dead_player", DetectionResult(True, 0.95, {}))
        manager.handle_result("dead_player", DetectionResult(False, 0.0, {}))

    text = out.getvalue()
    assert "Maple detection: player dead prompt detected." in text
    assert "Maple alert: player dead prompt." in text
    assert "Maple detection: player dead prompt cleared." in text


def test_player_alert_repeats_every_15_seconds_while_present() -> None:
    config = make_config()
    config["alerts"]["minimap_repeat_seconds"] = 15
    with tempfile.TemporaryDirectory() as temp_dir:
        config["_config_dir"] = temp_dir
        manager = AlertManager(config, logging.getLogger("test_minimap_repeat"))
        real_monotonic = maple_alert.time.monotonic
        now = {"value": 1000.0}

        def fake_monotonic() -> float:
            return now["value"]

        maple_alert.time.monotonic = fake_monotonic
        try:
            assert manager.handle_result("minimap_red", DetectionResult(True, 0.9, {"red_pixels": 60}))
            now["value"] += 14.9
            assert not manager.handle_result("minimap_red", DetectionResult(True, 0.9, {"red_pixels": 60}))
            now["value"] += 0.1
            assert manager.handle_result("minimap_red", DetectionResult(True, 0.9, {"red_pixels": 60}))
        finally:
            maple_alert.time.monotonic = real_monotonic


def test_dead_player_alert_repeats_while_present() -> None:
    config = make_config()
    config["alerts"]["dead_player_repeat_seconds"] = 30
    with tempfile.TemporaryDirectory() as temp_dir:
        config["_config_dir"] = temp_dir
        manager = AlertManager(config, logging.getLogger("test_dead_repeat"))
        real_monotonic = maple_alert.time.monotonic
        now = {"value": 2000.0}

        def fake_monotonic() -> float:
            return now["value"]

        maple_alert.time.monotonic = fake_monotonic
        try:
            assert manager.handle_result("dead_player", DetectionResult(True, 0.95, {}))
            now["value"] += 29.9
            assert not manager.handle_result("dead_player", DetectionResult(True, 0.95, {}))
            now["value"] += 0.1
            assert manager.handle_result("dead_player", DetectionResult(True, 0.95, {}))
        finally:
            maple_alert.time.monotonic = real_monotonic


def test_remote_alert_sends_once_per_dead_player_instance() -> None:
    config = make_config()
    config["alerts"]["dead_player_repeat_seconds"] = 30
    with tempfile.TemporaryDirectory() as temp_dir:
        config["_config_dir"] = temp_dir
        manager = AlertManager(config, logging.getLogger("test_dead_remote_once"))
        real_monotonic = maple_alert.time.monotonic
        real_remote = maple_alert.send_remote_notifications
        now = {"value": 3000.0}
        calls: list[str] = []

        def fake_monotonic() -> float:
            return now["value"]

        def fake_remote(_config: dict, _logger: logging.Logger, message: str, post_func=None) -> None:
            _ = post_func
            calls.append(message)

        maple_alert.time.monotonic = fake_monotonic
        maple_alert.send_remote_notifications = fake_remote
        try:
            assert manager.handle_result("dead_player", DetectionResult(True, 0.95, {}))
            now["value"] += 30.0
            assert manager.handle_result("dead_player", DetectionResult(True, 0.95, {}))
            assert len(calls) == 1

            manager.handle_result("dead_player", DetectionResult(False, 0.0, {}))
            now["value"] += 1.0
            assert manager.handle_result("dead_player", DetectionResult(True, 0.95, {}))
            assert len(calls) == 2
        finally:
            maple_alert.time.monotonic = real_monotonic
            maple_alert.send_remote_notifications = real_remote


def test_remote_alert_sends_once_per_minimap_player_instance() -> None:
    config = make_config()
    config["alerts"]["minimap_required_seconds"] = 0
    config["alerts"]["minimap_repeat_seconds"] = 15
    with tempfile.TemporaryDirectory() as temp_dir:
        config["_config_dir"] = temp_dir
        manager = AlertManager(config, logging.getLogger("test_player_remote_once"))
        real_monotonic = maple_alert.time.monotonic
        real_remote = maple_alert.send_remote_notifications
        now = {"value": 4000.0}
        calls: list[str] = []

        def fake_monotonic() -> float:
            return now["value"]

        def fake_remote(_config: dict, _logger: logging.Logger, message: str, post_func=None) -> None:
            _ = post_func
            calls.append(message)

        maple_alert.time.monotonic = fake_monotonic
        maple_alert.send_remote_notifications = fake_remote
        try:
            assert manager.handle_result("minimap_red", DetectionResult(True, 0.95, {"red_pixels": 60}))
            now["value"] += 15.0
            assert manager.handle_result("minimap_red", DetectionResult(True, 0.95, {"red_pixels": 60}))
            assert len(calls) == 1

            manager.handle_result("minimap_red", DetectionResult(False, 0.0, {}))
            now["value"] += 1.0
            assert manager.handle_result("minimap_red", DetectionResult(True, 0.95, {"red_pixels": 60}))
            assert len(calls) == 2
        finally:
            maple_alert.time.monotonic = real_monotonic
            maple_alert.send_remote_notifications = real_remote


if __name__ == "__main__":
    test_captcha_prints_alert_and_clear()
    test_dead_player_prints_alert_and_clear()
    test_minimap_prints_detected_alert_and_clear()
    test_player_alert_repeats_every_15_seconds_while_present()
    test_dead_player_alert_repeats_while_present()
    test_remote_alert_sends_once_per_dead_player_instance()
    test_remote_alert_sends_once_per_minimap_player_instance()
    print("alert state print tests passed")
