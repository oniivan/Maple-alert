from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from maple_alert import (  # noqa: E402
    CaptchaDetector,
    Rect,
    crop_bgr,
    detect_minimap_red,
    load_config,
    roi_to_rect,
    runtime_pixel_scale,
    scale_int,
    set_runtime_scale,
    setup_logging,
)


def hsv_pixel(h: int, s: int, v: int) -> tuple[int, int, int]:
    hsv = np.uint8([[[h, s, v]]])
    bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)[0, 0]
    return int(bgr[0]), int(bgr[1]), int(bgr[2])


def synthetic_captcha_full(config: dict, width: int, height: int) -> np.ndarray:
    base_rect = Rect(0, 0, width, height)
    set_runtime_scale(config, base_rect)
    pixel_scale = runtime_pixel_scale(config)
    roi = roi_to_rect(base_rect, config["roi"]["captcha"])
    full = np.zeros((height, width, 3), dtype=np.uint8)
    full[:, :] = hsv_pixel(70, 80, 90)

    patch_w = scale_int(config["detection"]["captcha"]["patch_width"], pixel_scale)
    patch_h = scale_int(config["detection"]["captcha"]["patch_height"], pixel_scale)
    x = roi.left + max(0, (roi.width - patch_w) // 2)
    y = roi.top + max(0, (roi.height - patch_h) // 2)
    full[y : y + patch_h, x : x + patch_w] = hsv_pixel(105, 154, 186)

    region_x1 = x + int(round(patch_w * config["detection"]["captcha"]["patch_dark_region_x1"]))
    region_y1 = y + int(round(patch_h * config["detection"]["captcha"]["patch_dark_region_y1"]))
    region_x2 = x + int(round(patch_w * config["detection"]["captcha"]["patch_dark_region_x2"]))
    region_y2 = y + int(round(patch_h * config["detection"]["captcha"]["patch_dark_region_y2"]))
    dark_w = max(1, int(round((region_x2 - region_x1) * 0.70)))
    dark_h = max(1, int(round((region_y2 - region_y1) * 0.50)))
    full[region_y1 : region_y1 + dark_h, region_x2 - dark_w : region_x2] = hsv_pixel(0, 0, 50)
    return full


def synthetic_minimap_roi(config: dict, full_width: int, full_height: int) -> np.ndarray:
    base_rect = Rect(0, 0, full_width, full_height)
    set_runtime_scale(config, base_rect)
    pixel_scale = runtime_pixel_scale(config)
    roi = roi_to_rect(base_rect, config["roi"]["minimap"])
    minimap = np.zeros((roi.height, roi.width, 3), dtype=np.uint8)
    minimap[:, :] = hsv_pixel(110, 80, 45)

    frame_color = hsv_pixel(0, 0, 180)
    frame_right = min(scale_int(310, pixel_scale), roi.width)
    minimap[
        scale_int(32, pixel_scale) : min(scale_int(74, pixel_scale), roi.height),
        :frame_right,
    ] = frame_color
    bottom_y = min(scale_int(285, pixel_scale), roi.height - 1)
    minimap[bottom_y : min(bottom_y + scale_int(3, pixel_scale), roi.height), :frame_right] = frame_color

    left = scale_int(8, pixel_scale)
    top = scale_int(78, pixel_scale)
    dot_size = max(5, scale_int(9, pixel_scale))
    dot_x = min(roi.width - dot_size, left + scale_int(100, pixel_scale))
    dot_y = min(roi.height - dot_size, top + scale_int(90, pixel_scale))
    dot_template = np.array(
        [
            [0, 0, 1, 1, 1, 1, 1, 0, 0],
            [0, 1, 1, 1, 1, 1, 1, 1, 0],
            [1, 1, 1, 1, 1, 1, 1, 1, 1],
            [1, 1, 1, 1, 1, 1, 1, 1, 1],
            [1, 1, 1, 1, 1, 1, 1, 1, 1],
            [1, 1, 1, 1, 1, 1, 1, 1, 1],
            [1, 1, 1, 1, 1, 1, 1, 1, 1],
            [0, 1, 1, 1, 1, 1, 1, 1, 0],
            [0, 0, 1, 1, 1, 1, 1, 0, 0],
        ],
        dtype=np.uint8,
    )
    dot_mask = cv2.resize(dot_template, (dot_size, dot_size), interpolation=cv2.INTER_NEAREST).astype(bool)
    minimap[dot_y : dot_y + dot_size, dot_x : dot_x + dot_size][dot_mask] = (0, 0, 255)
    return minimap


def main() -> int:
    config = load_config(ROOT / "config.example.toml")
    config["detection"]["captcha"]["use_template"] = False
    logger = setup_logging(config)
    detector = CaptchaDetector(config, logger)

    cases = [
        ("720p", 1280, 720),
        ("1080p-reference", 1919, 1079),
        ("1440p", 2560, 1440),
        ("weird-wide", 1600, 900),
    ]
    failures = 0

    for label, width, height in cases:
        full = synthetic_captcha_full(config, width, height)
        base_rect = Rect(0, 0, width, height)
        set_runtime_scale(config, base_rect)
        captcha_roi = crop_bgr(full, roi_to_rect(base_rect, config["roi"]["captcha"]))
        captcha_result = detector.detect(captcha_roi)
        scale = runtime_pixel_scale(config)
        ok = captcha_result.detected
        print(
            f"{'PASS' if ok else 'FAIL'} captcha {label}: "
            f"{width}x{height} pixel_scale={scale:.4f} detected={captcha_result.detected} "
            f"info={captcha_result.info.get('heuristic')}"
        )
        failures += 0 if ok else 1

        minimap = synthetic_minimap_roi(config, width, height)
        set_runtime_scale(config, base_rect)
        red_result, _ = detect_minimap_red(minimap, config)
        ok = red_result.detected and int(red_result.info.get("dot_count", 0)) == 1
        print(
            f"{'PASS' if ok else 'FAIL'} red-dot {label}: "
            f"{width}x{height} pixel_scale={scale:.4f} detected={red_result.detected} "
            f"dot_count={red_result.info.get('dot_count')} info={red_result.info}"
        )
        failures += 0 if ok else 1

    print(f"auto-scaling synthetic tests: cases={len(cases) * 2} failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
