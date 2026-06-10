from __future__ import annotations

import copy
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from detectors.dead_player import detect_dead_player  # noqa: E402
from maple_alert import DEFAULT_CONFIG, Rect, crop_bgr, roi_to_rect, set_runtime_scale  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = ROOT / "screenshots" / "dead"
TEMPLATE = FIXTURE_DIR / "dead main prompt.png"


def expected_from_name(path: Path) -> bool:
    name = path.name.casefold()
    if name.startswith("not dead"):
        return False
    if name.startswith("dead ") and name != "dead main prompt.png":
        return True
    raise AssertionError(f"unexpected fixture name: {path.name}")


def test_dead_player_image_fixtures() -> None:
    paths = sorted(
        path
        for path in FIXTURE_DIR.glob("*.png")
        if path.name.casefold() != "dead main prompt.png"
    )
    if not paths:
        print(f"dead player image fixtures skipped: no files in {FIXTURE_DIR}")
        return

    config = copy.deepcopy(DEFAULT_CONFIG)
    config["_config_dir"] = str(ROOT)
    config["detection"]["dead_player"]["enabled"] = True
    config["detection"]["dead_player"]["template_path"] = str(TEMPLATE)
    failures = 0

    for path in paths:
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        assert image is not None, path
        height, width = image.shape[:2]
        base_rect = Rect(0, 0, width, height)
        set_runtime_scale(config, base_rect)
        roi = roi_to_rect(base_rect, config["roi"]["dead_player"])
        roi_bgr = crop_bgr(image, roi)
        result = detect_dead_player(roi_bgr, config)
        expected = expected_from_name(path)
        ok = result.detected is expected
        print(
            f"{'PASS' if ok else 'FAIL'} {path.name}: "
            f"expected={expected} detected={result.detected} "
            f"score={result.confidence:.4f} info={result.info}"
        )
        if not ok:
            failures += 1

    assert failures == 0


if __name__ == "__main__":
    test_dead_player_image_fixtures()
    print("dead player image tests passed")
