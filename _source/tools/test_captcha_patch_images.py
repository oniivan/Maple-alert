from __future__ import annotations

import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from maple_alert import CaptchaDetector, Rect, crop_bgr, load_config, roi_to_rect, set_runtime_scale, setup_logging  # noqa: E402


USAGE = (
    "Usage: python _source/tools/test_captcha_patch_images.py "
    "C:/path/to/screenshot-fixtures"
)


def expected_captcha(path: Path) -> bool | None:
    name = path.name.casefold()
    if name.startswith("noncaptcha"):
        return False
    if name.startswith("captcha"):
        return True
    return None


def main() -> int:
    if len(sys.argv) != 2:
        print(USAGE)
        print("This detector regression check is optional and requires private screenshot fixtures.")
        return 2

    image_dir = Path(sys.argv[1])
    if not image_dir.is_dir():
        print(f"Fixture directory not found: {image_dir}")
        print(USAGE)
        return 2

    paths = sorted(
        path
        for path in image_dir.glob("*.png")
        if expected_captcha(path) is not None
    )
    if not paths:
        print(f"No captcha/noncaptcha test screenshots found in {image_dir}")
        return 2

    config = load_config(ROOT / "config.example.toml")
    config["detection"]["captcha"]["use_template"] = False
    config["detection"]["captcha"]["use_heuristic"] = True
    logger = setup_logging(config)
    detector = CaptchaDetector(config, logger)

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
        roi = crop_bgr(image, roi_to_rect(base_rect, config["roi"]["captcha"]))
        result = detector.detect(roi)
        expected = expected_captcha(path)
        method = result.info.get("heuristic", {}).get("method")
        patch_size = result.info.get("heuristic", {}).get("patch_size")
        uses_patch = method == "blue_patch_with_dark_corner" and patch_size == [145, 100]
        ok = result.detected == expected and (not expected or uses_patch)
        status = "PASS" if ok else "FAIL"
        print(
            f"{status} {path.name}: expected={expected} detected={result.detected} "
            f"confidence={result.confidence:.4f} method={method} info={result.info.get('heuristic')}"
        )
        failures += 0 if ok else 1

    print(f"captcha patch image tests: files={len(paths)} failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
