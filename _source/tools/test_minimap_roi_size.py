from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from maple_alert import Rect, load_config, roi_to_rect


ROOT = Path(__file__).resolve().parents[1]


def test_minimap_roi_matches_largest_reference_minimap_area() -> None:
    config = load_config(ROOT / "config.example.toml")
    roi = roi_to_rect(Rect(0, 0, 1919, 1079), config["roi"]["minimap"])

    assert roi.left == 0
    assert roi.top == 0
    assert roi.width == 460
    assert roi.height == 420


if __name__ == "__main__":
    test_minimap_roi_matches_largest_reference_minimap_area()
    print("minimap ROI size tests passed")
