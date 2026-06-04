from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from maple_alert import (
    SYSTEM_VOLUME_PROMPT_REPEAT_SECONDS,
    SYSTEM_VOLUME_PROMPT_SECONDS,
    SYSTEM_VOLUME_WARNING_PERCENT,
    SystemVolumeState,
    SystemVolumePromptTracker,
    activate_tk_window,
    notify_system_volume_warning,
    read_alert_volume_percent,
    read_ignore_system_volume_warning,
    system_volume_button_state,
    system_volume_warning_notification_message,
    write_alert_volume_percent,
    write_ignore_system_volume_warning,
)


def test_system_volume_warning_threshold_is_below_30_percent() -> None:
    assert SYSTEM_VOLUME_WARNING_PERCENT == 30
    assert SystemVolumeState(29, False).needs_attention
    assert not SystemVolumeState(30, False).needs_attention
    assert not SystemVolumeState(69, False).needs_attention
    assert not SystemVolumeState(89, False).needs_attention


def test_muted_system_volume_always_needs_attention() -> None:
    assert SystemVolumeState(100, True).needs_attention


def test_ignoring_system_volume_warning_preserves_alert_volume() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        config = {
            "_config_dir": temp_dir,
            "alerts": {
                "alert_volume_percent": 200,
                "alert_settings_file": "runtime/alert_settings.json",
            },
        }
        write_alert_volume_percent(config, 175)
        write_ignore_system_volume_warning(config, True)

        assert read_alert_volume_percent(config) == 175
        assert read_ignore_system_volume_warning(config)


def test_system_volume_button_only_shows_for_active_warning() -> None:
    assert not system_volume_button_state(False, False, False)["visible"]

    ignore_state = system_volume_button_state(True, False, True)
    assert ignore_state["visible"]
    assert ignore_state["label"] == "IGNORE"

    warn_pulse = system_volume_button_state(True, True, True)
    warn_dim = system_volume_button_state(True, True, False)
    assert warn_pulse["visible"]
    assert warn_pulse["label"] == "WARN"
    assert warn_pulse["fill"] != warn_dim["fill"]


def test_system_volume_prompt_waits_three_minutes_and_repeats_only_after_close() -> None:
    assert SYSTEM_VOLUME_PROMPT_SECONDS == 180
    assert SYSTEM_VOLUME_PROMPT_REPEAT_SECONDS == 180
    tracker = SystemVolumePromptTracker(hold_seconds=180, repeat_seconds=180)

    assert tracker.update(needs_attention=True, ignored=False, prompt_open=False, now=0) is False
    assert tracker.update(needs_attention=True, ignored=False, prompt_open=False, now=179) is False
    assert tracker.update(needs_attention=True, ignored=False, prompt_open=False, now=180) is True
    assert tracker.update(needs_attention=True, ignored=False, prompt_open=True, now=181) is False
    assert tracker.update(needs_attention=True, ignored=False, prompt_open=False, now=359) is False
    assert tracker.update(needs_attention=True, ignored=False, prompt_open=False, now=360) is True


def test_system_volume_prompt_resets_when_volume_recovers_or_is_ignored() -> None:
    tracker = SystemVolumePromptTracker(hold_seconds=180, repeat_seconds=180)

    assert tracker.update(needs_attention=True, ignored=False, prompt_open=False, now=0) is False
    assert tracker.update(needs_attention=False, ignored=False, prompt_open=False, now=120) is False
    assert tracker.update(needs_attention=True, ignored=False, prompt_open=False, now=200) is False
    assert tracker.update(needs_attention=True, ignored=False, prompt_open=False, now=379) is False
    assert tracker.update(needs_attention=True, ignored=False, prompt_open=False, now=380) is True
    assert tracker.update(needs_attention=True, ignored=True, prompt_open=False, now=381) is False


def test_system_volume_warning_notification_message_describes_muted_or_low_volume() -> None:
    muted_message = system_volume_warning_notification_message(SystemVolumeState(100, True))
    low_message = system_volume_warning_notification_message(SystemVolumeState(12, False))

    assert "system volume warning" in muted_message.casefold()
    assert "muted" in muted_message.casefold()
    assert "12%" in low_message
    assert "IGNORE" in low_message


def test_notify_system_volume_warning_sends_remote_message() -> None:
    calls: list[str] = []

    def fake_sender(config: dict, logger: object, message: str) -> None:
        calls.append(message)

    notify_system_volume_warning({}, SystemVolumeState(18, False), sender=fake_sender)

    assert len(calls) == 1
    assert "18%" in calls[0]
    assert "system volume warning" in calls[0].casefold()


class FakeWindow:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def deiconify(self) -> None:
        self.calls.append(("deiconify", ()))

    def lift(self) -> None:
        self.calls.append(("lift", ()))

    def attributes(self, *args: object) -> None:
        self.calls.append(("attributes", args))

    def focus_force(self) -> None:
        self.calls.append(("focus_force", ()))


def test_activate_tk_window_attempts_foreground_focus() -> None:
    fake = FakeWindow()

    activate_tk_window(fake)

    names = [name for name, _args in fake.calls]
    assert "deiconify" in names
    assert "lift" in names
    assert ("attributes", ("-topmost", True)) in fake.calls
    assert "focus_force" in names


if __name__ == "__main__":
    test_system_volume_warning_threshold_is_below_30_percent()
    test_muted_system_volume_always_needs_attention()
    test_ignoring_system_volume_warning_preserves_alert_volume()
    test_system_volume_button_only_shows_for_active_warning()
    test_system_volume_prompt_waits_three_minutes_and_repeats_only_after_close()
    test_system_volume_prompt_resets_when_volume_recovers_or_is_ignored()
    test_system_volume_warning_notification_message_describes_muted_or_low_volume()
    test_notify_system_volume_warning_sends_remote_message()
    test_activate_tk_window_attempts_foreground_focus()
    print("system volume warning tests passed")
