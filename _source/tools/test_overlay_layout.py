from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from maple_alert import (
    OVERLAY_COLLAPSED_HEIGHT,
    OVERLAY_FULL_HEIGHT,
    OVERLAY_PLAYER_VOLUME_LABEL,
    blend_hex_color,
    overlay_control_layout,
    overlay_drawer_target_height,
)


def test_overlay_drawer_uses_shorter_full_height_and_collapsed_bar() -> None:
    assert OVERLAY_FULL_HEIGHT < 126
    assert OVERLAY_COLLAPSED_HEIGHT == 34
    assert overlay_drawer_target_height(False) == OVERLAY_FULL_HEIGHT
    assert overlay_drawer_target_height(True) == OVERLAY_COLLAPSED_HEIGHT


def test_volume_meters_are_side_by_side_with_same_width() -> None:
    layout = overlay_control_layout()
    lie = layout["meters"]["captcha"]
    player = layout["meters"]["minimap_red"]

    assert layout["width"] == 340
    assert OVERLAY_PLAYER_VOLUME_LABEL == "PLAYER DETECT VOLUME"
    assert lie["outline"][1] == player["outline"][1]
    assert lie["outline"][3] == player["outline"][3]
    assert lie["outline"][2] < player["outline"][0]
    assert lie["fill_width"] == player["fill_width"]


def test_volume_fill_color_can_be_softened() -> None:
    assert blend_hex_color("#24d15d", "#10151b", 0.25) == "#1fa24c"


if __name__ == "__main__":
    test_overlay_drawer_uses_shorter_full_height_and_collapsed_bar()
    test_volume_meters_are_side_by_side_with_same_width()
    test_volume_fill_color_can_be_softened()
    print("overlay layout tests passed")
