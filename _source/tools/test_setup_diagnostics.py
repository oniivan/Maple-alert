from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from maple_alert import (  # noqa: E402
    DEFAULT_CONFIG,
    Rect,
    SystemVolumeState,
    build_redacted_config,
    build_setup_check_report,
    write_diagnostic_bundle,
    write_notification_settings,
)


def make_config(temp_dir: str) -> dict:
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["_config_dir"] = temp_dir
    config["telegram"]["bot_token"] = "tg-secret-token"
    config["telegram"]["chat_id"] = "123456789"
    config["discord"]["enabled"] = True
    config["discord"]["bot_token"] = "discord-secret-token"
    config["discord"]["user_id"] = "987654321"
    config["discord"]["webhook_url"] = "https://discord.com/api/webhooks/secret/webhook"
    return config


def test_redacted_config_removes_remote_alert_secrets() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        config = make_config(temp_dir)
        write_notification_settings(
            config,
            {
                "remote_enabled": True,
                "telegram": {
                    "enabled": True,
                    "bot_token": "runtime-tg-token",
                    "chat_id": "runtime-chat-id",
                },
                "discord": {
                    "enabled": True,
                    "bot_token": "runtime-discord-token",
                    "user_id": "runtime-user-id",
                    "webhook_url": "https://discord.com/api/webhooks/runtime/secret",
                },
            },
        )

        redacted = build_redacted_config(config)
        payload = json.dumps(redacted, sort_keys=True)

        assert "tg-secret-token" not in payload
        assert "discord-secret-token" not in payload
        assert "runtime-tg-token" not in payload
        assert "runtime-discord-token" not in payload
        assert "123456789" not in payload
        assert "987654321" not in payload
        assert "https://discord.com/api/webhooks" not in payload
        assert redacted["capture"]["window_title"] == "Maple"
        assert redacted["telegram"]["bot_token"] == "<set, redacted>"


def test_setup_check_report_shows_target_window_scale_and_volumes_without_secrets() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        config = make_config(temp_dir)
        windows = [
            ("Maple Alert", Rect(10, 10, 300, 200)),
            ("Maple Client", Rect(50, 60, 1919, 1079)),
        ]

        report = build_setup_check_report(
            config,
            Path(temp_dir) / "config.toml",
            windows=windows,
            system_volume_state=SystemVolumeState(88, False),
        )

        assert "Maple Client" in report
        assert "1919x1079" in report
        assert "pixel_scale=1.0000" in report
        assert "Lie Detect Volume: 200%" in report
        assert "Player Detect Volume: 200%" in report
        assert "tg-secret-token" not in report
        assert "discord-secret-token" not in report
        assert "123456789" not in report
        assert "987654321" not in report


def test_diagnostic_bundle_writes_redacted_text_files_only() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        config = make_config(temp_dir)
        config_path = Path(temp_dir) / "config.toml"
        log_path = Path(temp_dir) / "logs" / "detections.log"
        log_path.parent.mkdir(parents=True)
        log_path.write_text(
            "Telegram failed for https://api.telegram.org/bottg-secret-token/sendMessage\n"
            "Discord failed for https://discord.com/api/webhooks/secret/webhook\n",
            encoding="utf-8",
        )
        runtime_dir = Path(temp_dir) / "runtime"
        runtime_dir.mkdir()
        (runtime_dir / "heartbeat.json").write_text(
            json.dumps({"source": "window", "window_title": "Maple", "token": "heartbeat-secret"}),
            encoding="utf-8",
        )

        bundle_dir = write_diagnostic_bundle(
            config,
            config_path,
            output_root=Path(temp_dir) / "diagnostics",
            windows=[],
            system_volume_state=SystemVolumeState(75, False),
        )
        combined = "\n".join(path.read_text(encoding="utf-8") for path in bundle_dir.rglob("*.txt"))
        combined += json.dumps(
            json.loads((bundle_dir / "config_redacted.json").read_text(encoding="utf-8")),
            sort_keys=True,
        )
        combined += json.dumps(
            json.loads((bundle_dir / "runtime" / "heartbeat.json").read_text(encoding="utf-8")),
            sort_keys=True,
        )

        assert "tg-secret-token" not in combined
        assert "discord.com/api/webhooks/secret" not in combined
        assert "heartbeat-secret" not in combined
        assert list(bundle_dir.rglob("*.png")) == []
        assert (bundle_dir / "README.txt").is_file()


if __name__ == "__main__":
    test_redacted_config_removes_remote_alert_secrets()
    test_setup_check_report_shows_target_window_scale_and_volumes_without_secrets()
    test_diagnostic_bundle_writes_redacted_text_files_only()
    print("setup diagnostics tests passed")
