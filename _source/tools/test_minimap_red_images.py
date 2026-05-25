from __future__ import annotations

import re
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from maple_alert import Rect, crop_bgr, detect_minimap_red, load_config, roi_to_rect, set_runtime_scale  # noqa: E402


def expected_count(path: Path) -> int:
    match = re.match(r"(\d+)", path.name)
    if not match:
        raise ValueError(f"Could not read expected red-dot count from {path.name}")
    return int(match.group(1))


def main() -> int:
    image_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("D:/screens")
    paths = sorted(image_dir.glob("*red dot*.png"))
    if not paths:
        print(f"No red-dot test screenshots found in {image_dir}")
        return 2

    config = load_config(ROOT / "config.example.toml")
    config["detection"]["minimap"]["enabled"] = True

    failures = 0
    for path in paths:
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            print(f"FAIL {path.name}: could not read image")
            failures += 1
            continue

        height, width = image.shape[:2]
        base_rect = Rect(0, 0, width, height)
        set_runtime_scale(config, base_rect)
        roi = roi_to_rect(base_rect, config["roi"]["minimap"])
        minimap = crop_bgr(image, roi)
        result, _ = detect_minimap_red(minimap, config)

        expected = expected_count(path)
        actual = int(result.info.get("dot_count", 1 if result.detected else 0))
        ok = actual == expected and result.detected == (expected > 0)
        status = "PASS" if ok else "FAIL"
        print(
            f"{status} {path.name}: expected={expected} actual={actual} "
            f"detected={result.detected} info={result.info}"
        )
        failures += 0 if ok else 1

    print(f"red-dot image tests: files={len(paths)} failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
