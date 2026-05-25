from __future__ import annotations

import io
import logging
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from maple_alert import AlertManager, DetectionResult


def make_config() -> dict:
    return {
        "_config_dir": str(Path.cwd()),
        "alerts": {
            "audible": False,
            "safe_mode": True,
            "telegram_enabled": False,
            "captcha_repeat_seconds": 30,
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


if __name__ == "__main__":
    test_captcha_prints_alert_and_clear()
    test_minimap_prints_detected_alert_and_clear()
    print("alert state print tests passed")
