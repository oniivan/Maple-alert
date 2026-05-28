from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from maple_alert import (
    notification_service_enabled,
    read_notification_settings,
    send_discord_notification,
    send_telegram_notification,
    write_notification_settings,
)


class FakeResponse:
    def __init__(self, payload: dict | None = None) -> None:
        self.payload = payload or {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class FakeLogger:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def info(self, message: str, *args: object) -> None:
        self.messages.append(("info", message % args if args else message))

    def warning(self, message: str, *args: object) -> None:
        self.messages.append(("warning", message % args if args else message))


def make_config(temp_dir: str) -> dict:
    return {
        "_config_dir": temp_dir,
        "alerts": {
            "safe_mode": True,
            "telegram_enabled": True,
        },
        "notifications": {
            "settings_file": "runtime/notification_settings.json",
            "remote_enabled": False,
        },
        "telegram": {
            "bot_token": "",
            "chat_id": "",
        },
        "discord": {
            "enabled": False,
            "bot_token": "",
            "user_id": "",
            "webhook_url": "",
        },
    }


def test_notification_settings_are_persisted_and_enable_safe_mode_override() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        config = make_config(temp_dir)

        write_notification_settings(
            config,
            {
                "remote_enabled": True,
                "telegram": {"enabled": True, "bot_token": "tg-token", "chat_id": "12345"},
                "discord": {"enabled": True, "bot_token": "dc-token", "user_id": "98765"},
            },
        )

        settings = read_notification_settings(config)
        assert settings["remote_enabled"] is True
        assert settings["telegram"]["chat_id"] == "12345"
        assert settings["discord"]["user_id"] == "98765"
        assert notification_service_enabled(config, "telegram") is True
        assert notification_service_enabled(config, "discord") is True


def test_telegram_notification_uses_runtime_settings() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        config = make_config(temp_dir)
        write_notification_settings(
            config,
            {
                "remote_enabled": True,
                "telegram": {"enabled": True, "bot_token": "tg-token", "chat_id": "12345"},
            },
        )
        calls: list[dict] = []

        def fake_post(url: str, **kwargs: object) -> FakeResponse:
            calls.append({"url": url, **kwargs})
            return FakeResponse()

        assert send_telegram_notification(config, FakeLogger(), "hello", post_func=fake_post) is True
        assert calls[0]["url"] == "https://api.telegram.org/bottg-token/sendMessage"
        assert calls[0]["data"] == {"chat_id": "12345", "text": "hello"}


def test_runtime_service_disable_overrides_legacy_telegram_enabled() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        config = make_config(temp_dir)
        write_notification_settings(
            config,
            {
                "remote_enabled": True,
                "telegram": {"enabled": False, "bot_token": "tg-token", "chat_id": "12345"},
            },
        )

        assert notification_service_enabled(config, "telegram") is False


def test_legacy_safe_mode_false_still_allows_telegram() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        config = make_config(temp_dir)
        config["alerts"]["safe_mode"] = False
        config["telegram"]["bot_token"] = "tg-token"
        config["telegram"]["chat_id"] = "12345"

        assert notification_service_enabled(config, "telegram") is True


def test_discord_dm_notification_uses_user_id_runtime_settings() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        config = make_config(temp_dir)
        write_notification_settings(
            config,
            {
                "remote_enabled": True,
                "discord": {"enabled": True, "bot_token": "dc-token", "user_id": "98765"},
            },
        )
        calls: list[dict] = []

        def fake_post(url: str, **kwargs: object) -> FakeResponse:
            calls.append({"url": url, **kwargs})
            if url.endswith("/users/@me/channels"):
                return FakeResponse({"id": "channel-1"})
            return FakeResponse()

        assert send_discord_notification(config, FakeLogger(), "hello", post_func=fake_post) is True
        assert calls[0]["url"] == "https://discord.com/api/v10/users/@me/channels"
        assert calls[0]["json"] == {"recipient_id": "98765"}
        assert calls[1]["url"] == "https://discord.com/api/v10/channels/channel-1/messages"
        assert calls[1]["json"] == {"content": "hello"}


if __name__ == "__main__":
    test_notification_settings_are_persisted_and_enable_safe_mode_override()
    test_telegram_notification_uses_runtime_settings()
    test_runtime_service_disable_overrides_legacy_telegram_enabled()
    test_legacy_safe_mode_false_still_allows_telegram()
    test_discord_dm_notification_uses_user_id_runtime_settings()
    print("notification settings tests passed")
