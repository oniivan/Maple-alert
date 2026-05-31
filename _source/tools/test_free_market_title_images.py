from __future__ import annotations

import copy
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from detectors.minimap_title import detect_free_market_title  # noqa: E402
from maple_alert import DEFAULT_CONFIG, Rect, crop_bgr, roi_to_rect, set_runtime_scale  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = ROOT / "screenshots"
TEMPLATE = ROOT / "templates" / "free_market_title.png"
KNOWN_NEGATIVE_FIXTURES = {"free market (2).png"}


def expected_from_name(path: Path) -> bool:
    name = path.name.casefold()
    if name in KNOWN_NEGATIVE_FIXTURES:
        return False
    if name.startswith("not free market"):
        return False
    if name.startswith("free market"):
        return True
    raise AssertionError(f"unexpected fixture name: {path.name}")


def test_free_market_title_image_fixtures() -> None:
    paths = sorted(FIXTURE_DIR.glob("*free market*.png"))
    if not paths:
        print(f"free market title image fixtures skipped: no files in {FIXTURE_DIR}")
        return

    config = copy.deepcopy(DEFAULT_CONFIG)
    config["_config_dir"] = str(ROOT)
    config["detection"]["free_market"]["enabled"] = True
    config["detection"]["free_market"]["template_path"] = str(TEMPLATE)
    failures = 0

    for path in paths:
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        assert image is not None, path
        height, width = image.shape[:2]
        base_rect = Rect(0, 0, width, height)
        set_runtime_scale(config, base_rect)
        minimap = crop_bgr(image, roi_to_rect(base_rect, config["roi"]["minimap"]))
        result = detect_free_market_title(minimap, config)
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
    test_free_market_title_image_fixtures()
    print("free market title image tests passed")
