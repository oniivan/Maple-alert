from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from maple_alert import DEFAULT_CONFIG, capture_interval_seconds


def test_default_capture_cadence_is_four_seconds() -> None:
    config = copy.deepcopy(DEFAULT_CONFIG)

    assert capture_interval_seconds(config) == 4.0


def test_sub_one_fps_is_allowed_for_low_cpu_polling() -> None:
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["capture"]["fps"] = 0.25

    assert capture_interval_seconds(config) == 4.0


if __name__ == "__main__":
    test_default_capture_cadence_is_four_seconds()
    test_sub_one_fps_is_allowed_for_low_cpu_polling()
    print("capture cadence tests passed")
