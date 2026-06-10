from __future__ import annotations

import io
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from maple_alert import alert_segments_for_kind, synthesize_alert_wav_bytes, volume_to_pcm_amplitude


def read_peak_and_duration(wav_bytes: bytes) -> tuple[int, float]:
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        frame_rate = wav.getframerate()
        frame_count = wav.getnframes()
        frames = wav.readframes(frame_count)
    samples = [
        int.from_bytes(frames[i : i + 2], "little", signed=True)
        for i in range(0, len(frames), 2)
    ]
    return max(abs(sample) for sample in samples), frame_count / frame_rate


def test_captcha_wav_matches_beep_durations() -> None:
    assert alert_segments_for_kind("captcha") == [(1300, 450), (1600, 450)]
    assert alert_segments_for_kind("dead_player") == alert_segments_for_kind("captcha")
    peak, duration = read_peak_and_duration(synthesize_alert_wav_bytes("captcha", 100))
    assert 0.88 <= duration <= 0.92
    assert peak == volume_to_pcm_amplitude(100)


def test_volume_percent_changes_pcm_amplitude() -> None:
    low_peak, _ = read_peak_and_duration(synthesize_alert_wav_bytes("captcha", 25))
    normal_peak, _ = read_peak_and_duration(synthesize_alert_wav_bytes("captcha", 100))
    high_peak, _ = read_peak_and_duration(synthesize_alert_wav_bytes("captcha", 200))
    max_peak, _ = read_peak_and_duration(synthesize_alert_wav_bytes("captcha", 250))
    boosted_peak, _ = read_peak_and_duration(synthesize_alert_wav_bytes("captcha", 300))

    assert low_peak < normal_peak < high_peak < max_peak
    assert max_peak < boosted_peak
    assert high_peak == normal_peak * 2


if __name__ == "__main__":
    test_captcha_wav_matches_beep_durations()
    test_volume_percent_changes_pcm_amplitude()
    print("alert wav generation tests passed")
