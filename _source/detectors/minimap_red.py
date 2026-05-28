from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from vision_core import (
    DetectionResult,
    Rect,
    crop_bgr,
    runtime_pixel_scale,
    scale_ceil,
    scale_floor,
    scale_int,
)


def locate_minimap_content_rect(bgr: np.ndarray, config: dict[str, Any]) -> Rect:
    height, width = bgr.shape[:2]
    pixel_scale = runtime_pixel_scale(config)
    search_h = min(scale_int(420, pixel_scale), height)
    search_w = min(scale_int(460, pixel_scale), width)
    search = bgr[:search_h, :search_w]
    hsv = cv2.cvtColor(search, cv2.COLOR_BGR2HSV)
    _, saturation, value = cv2.split(hsv)

    # The minimap has a bright low-saturation frame. Use the title/header width
    # to infer the right edge, then crop to the dark map content below it.
    frame_mask = (((value > 135) & (saturation < 95)).astype(np.uint8)) * 255
    header_top = min(scale_int(32, pixel_scale), frame_mask.shape[0])
    header_bottom = min(scale_int(74, pixel_scale), frame_mask.shape[0])
    header_rows = frame_mask[header_top:header_bottom, :]
    frame_right = 0
    if header_rows.size:
        cols = np.where(header_rows.sum(axis=0) > 255 * scale_int(8, pixel_scale))[0]
        if len(cols):
            groups: list[tuple[int, int]] = []
            start = previous = int(cols[0])
            for raw_col in cols[1:]:
                col = int(raw_col)
                if col - previous > scale_int(8, pixel_scale):
                    groups.append((start, previous))
                    start = col
                previous = col
            groups.append((start, previous))
            groups = [
                group
                for group in groups
                if group[0] < scale_int(40, pixel_scale)
                and group[1] - group[0] > scale_int(180, pixel_scale)
            ]
            if groups:
                frame_right = groups[0][1] + 1

    if not frame_right:
        frame_right = min(scale_int(310, pixel_scale), width)

    left = min(scale_int(8, pixel_scale), max(0, width - 1))
    top = min(scale_int(78, pixel_scale), max(0, height - 1))
    right = max(left + scale_int(80, pixel_scale), min(frame_right - scale_int(8, pixel_scale), width))
    bottom = 0
    for y in range(scale_int(250, pixel_scale), min(scale_int(420, pixel_scale), frame_mask.shape[0])):
        segment = frame_mask[y, left:right]
        if len(segment) and np.count_nonzero(segment) > 0.65 * max(1, right - left):
            bottom = y - scale_int(3, pixel_scale)
            break
    if not bottom:
        bottom = min(top + scale_int(340, pixel_scale), height)

    bottom = max(top + 1, min(bottom, height))
    right = max(left + 1, min(right, width))
    return Rect(left, top, right - left, bottom - top)


def detect_minimap_red(bgr: np.ndarray, config: dict[str, Any]) -> tuple[DetectionResult, np.ndarray]:
    red_cfg = config["detection"]["minimap"]
    if not bool(red_cfg.get("enabled", True)):
        mask = np.zeros(bgr.shape[:2], dtype=np.uint8)
        info = {
            "enabled": False,
            "red_pixels": 0,
            "red_percent": 0.0,
            "largest_blob_area": 0.0,
            "largest_blob_box": None,
            "reason": "minimap_red_disabled",
        }
        return DetectionResult(False, 0.0, info), mask

    content_rect = locate_minimap_content_rect(bgr, config)
    content_bgr = crop_bgr(bgr, content_rect)
    hsv = cv2.cvtColor(content_bgr, cv2.COLOR_BGR2HSV)
    hue, saturation, value = cv2.split(hsv)

    hue_max = int(red_cfg.get("red_hue_max", 8))
    hue_wrap_min = int(red_cfg.get("red_hue_wrap_min", 174))
    sat_min = int(red_cfg["saturation_min"])
    val_min = int(red_cfg["value_min"])
    content_mask = (
        ((hue <= hue_max) | (hue >= hue_wrap_min))
        & (saturation >= sat_min)
        & (value >= val_min)
    ).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    content_mask = cv2.morphologyEx(content_mask, cv2.MORPH_OPEN, kernel, iterations=1)

    mask = np.zeros(bgr.shape[:2], dtype=np.uint8)
    mask[
        content_rect.top : content_rect.bottom,
        content_rect.left : content_rect.right,
    ] = content_mask

    red_pixels = int(cv2.countNonZero(content_mask))
    total_pixels = max(1, content_bgr.shape[0] * content_bgr.shape[1])
    red_percent = red_pixels / float(total_pixels)

    contours, _ = cv2.findContours(content_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    dot_candidates: list[dict[str, Any]] = []
    rejected_blob_count = 0
    pixel_scale = runtime_pixel_scale(config)
    area_scale = pixel_scale * pixel_scale
    min_width = scale_floor(red_cfg.get("dot_width_min", 8), pixel_scale)
    max_width = scale_ceil(red_cfg.get("dot_width_max", 13), pixel_scale)
    min_height = scale_floor(red_cfg.get("dot_height_min", 8), pixel_scale)
    max_height = scale_ceil(red_cfg.get("dot_height_max", 13), pixel_scale)
    min_area = float(red_cfg.get("dot_area_min", 42.0)) * area_scale
    max_area = float(red_cfg.get("dot_area_max", 85.0)) * area_scale
    min_circularity = float(red_cfg.get("dot_circularity_min", 0.85))
    min_extent = float(red_cfg.get("dot_extent_min", 0.53))
    min_count = scale_floor(red_cfg.get("dot_pixel_count_min", red_cfg.get("dot_count_min", 50)), area_scale)
    min_mean_saturation = float(red_cfg.get("dot_mean_saturation_min", 240))
    min_mean_value = float(red_cfg.get("dot_mean_value_min", 220))

    for contour in contours:
        area = float(cv2.contourArea(contour))
        x, y, width, height = cv2.boundingRect(contour)
        perimeter = cv2.arcLength(contour, True)
        circularity = 0.0 if perimeter == 0 else float(4 * np.pi * area / (perimeter * perimeter))
        extent = float(area / max(1, width * height))
        contour_mask = np.zeros(content_mask.shape, dtype=np.uint8)
        cv2.drawContours(contour_mask, [contour], -1, 255, -1)
        contour_pixels = hsv[contour_mask > 0]
        mean_saturation = float(np.mean(contour_pixels[:, 1])) if contour_pixels.size else 0.0
        mean_value = float(np.mean(contour_pixels[:, 2])) if contour_pixels.size else 0.0
        pixel_count = int(np.count_nonzero(content_mask[y : y + height, x : x + width]))

        is_dot = (
            min_width <= width <= max_width
            and min_height <= height <= max_height
            and min_area <= area <= max_area
            and circularity >= min_circularity
            and extent >= min_extent
            and pixel_count >= min_count
            and mean_saturation >= min_mean_saturation
            and mean_value >= min_mean_value
        )
        if not is_dot:
            rejected_blob_count += 1
            continue

        global_box = [
            int(content_rect.left + x),
            int(content_rect.top + y),
            int(width),
            int(height),
        ]
        dot_candidates.append(
            {
                "box": global_box,
                "content_box": [int(x), int(y), int(width), int(height)],
                "area": round(area, 2),
                "circularity": round(circularity, 3),
                "extent": round(extent, 3),
                "pixel_count": pixel_count,
                "mean_saturation": round(mean_saturation, 2),
                "mean_value": round(mean_value, 2),
            }
        )

    dot_candidates.sort(key=lambda item: (item["box"][1], item["box"][0]))
    dot_count = len(dot_candidates)
    detected = dot_count > 0
    confidence = 1.0 if detected else 0.0
    largest_blob_area = max((candidate["area"] for candidate in dot_candidates), default=0.0)
    largest_blob_box = dot_candidates[0]["box"] if dot_candidates else None

    info = {
        "enabled": True,
        "dot_count": dot_count,
        "dot_boxes": [candidate["box"] for candidate in dot_candidates],
        "dot_candidates": dot_candidates,
        "content_rect": content_rect.__dict__,
        "runtime_scale": config.get("_runtime_scale", {}),
        "red_pixels": red_pixels,
        "red_percent": round(red_percent, 6),
        "largest_blob_area": round(largest_blob_area, 2),
        "largest_blob_box": largest_blob_box,
        "rejected_blob_count": rejected_blob_count,
        "thresholds": {
            "runtime_pixel_scale": round(pixel_scale, 4),
            "hue": [0, hue_max, hue_wrap_min, 180],
            "saturation_min": sat_min,
            "value_min": val_min,
            "width": [min_width, max_width],
            "height": [min_height, max_height],
            "area": [min_area, max_area],
            "circularity_min": min_circularity,
            "extent_min": min_extent,
            "dot_pixel_count_min": min_count,
            "mean_saturation_min": min_mean_saturation,
            "mean_value_min": min_mean_value,
        },
    }
    return DetectionResult(detected, confidence, info), mask
