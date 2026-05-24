from __future__ import annotations

import json
import sys
import tempfile
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from maple_alert import (
    read_alert_volume_percent,
    synthesize_alert_wav_bytes,
    volume_to_pcm_amplitude,
    write_alert_volume_percent,
)


def make_config(temp_dir: str, alerts: dict | None = None) -> dict:
    base_alerts = {
        "alert_volume_percent": 200,
        "lie_detect_volume_percent": 180,
        "player_detected_volume_percent": 120,
        "alert_settings_file": "runtime/alert_settings.json",
    }
    if alerts:
        base_alerts.update(alerts)
    return {
        "_config_dir": temp_dir,
        "alerts": base_alerts,
    }


def wav_peak(wav_bytes: bytes) -> int:
    path = Path(tempfile.mkdtemp()) / "sample.wav"
    path.write_bytes(wav_bytes)
    with wave.open(str(path), "rb") as wav:
        frames = wav.readframes(wav.getnframes())
    samples = memoryview(frames).cast("h")
    return max(abs(int(sample)) for sample in samples)


def test_lie_and_player_volumes_are_persisted_separately() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        config = make_config(temp_dir)

        write_alert_volume_percent(config, 225, kind="captcha")
        write_alert_volume_percent(config, 75, kind="minimap_red")

        payload = json.loads((Path(temp_dir) / "runtime" / "alert_settings.json").read_text())
        assert payload["lie_detect_volume_percent"] == 225
        assert payload["player_detected_volume_percent"] == 75
        assert read_alert_volume_percent(config, kind="captcha") == 225
        assert read_alert_volume_percent(config, kind="minimap_red") == 75


def test_legacy_alert_volume_falls_back_for_both_alerts() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        config = make_config(
            temp_dir,
            {
                "alert_volume_percent": 165,
                "lie_detect_volume_percent": None,
                "player_detected_volume_percent": None,
            },
        )

        assert read_alert_volume_percent(config, kind="captcha") == 165
        assert read_alert_volume_percent(config, kind="minimap_red") == 165


def test_player_volume_controls_actual_wav_amplitude() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        config = make_config(temp_dir)
        write_alert_volume_percent(config, 50, kind="minimap_red")

        volume = read_alert_volume_percent(config, kind="minimap_red")
        peak = wav_peak(synthesize_alert_wav_bytes("minimap_red", volume))

        assert peak == volume_to_pcm_amplitude(50)


if __name__ == "__main__":
    test_lie_and_player_volumes_are_persisted_separately()
    test_legacy_alert_volume_falls_back_for_both_alerts()
    test_player_volume_controls_actual_wav_amplitude()
    print("alert volume settings tests passed")
