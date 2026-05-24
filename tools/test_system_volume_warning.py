from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from maple_alert import (
    SYSTEM_VOLUME_WARNING_PERCENT,
    SystemVolumeState,
    read_alert_volume_percent,
    read_ignore_system_volume_warning,
    system_volume_button_state,
    write_alert_volume_percent,
    write_ignore_system_volume_warning,
)


def test_system_volume_warning_threshold_is_below_70_percent() -> None:
    assert SYSTEM_VOLUME_WARNING_PERCENT == 70
    assert SystemVolumeState(69, False).needs_attention
    assert not SystemVolumeState(70, False).needs_attention
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


if __name__ == "__main__":
    test_system_volume_warning_threshold_is_below_70_percent()
    test_muted_system_volume_always_needs_attention()
    test_ignoring_system_volume_warning_preserves_alert_volume()
    test_system_volume_button_only_shows_for_active_warning()
    print("system volume warning tests passed")
