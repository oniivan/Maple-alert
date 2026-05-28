from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import mss
import numpy as np


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    def to_mss(self) -> dict[str, int]:
        return {
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
        }


@dataclass
class DetectionResult:
    detected: bool
    confidence: float
    info: dict[str, Any]


@dataclass(frozen=True)
class ScaleInfo:
    reference_width: int
    reference_height: int
    capture_width: int
    capture_height: int
    scale_x: float
    scale_y: float
    pixel_scale: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference": [self.reference_width, self.reference_height],
            "capture": [self.capture_width, self.capture_height],
            "scale_x": round(self.scale_x, 4),
            "scale_y": round(self.scale_y, 4),
            "pixel_scale": round(self.pixel_scale, 4),
        }


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def roi_to_rect(base: Rect, roi_cfg: dict[str, float]) -> Rect:
    x1 = clamp01(float(roi_cfg["x1"]))
    y1 = clamp01(float(roi_cfg["y1"]))
    x2 = clamp01(float(roi_cfg["x2"]))
    y2 = clamp01(float(roi_cfg["y2"]))
    if x2 <= x1:
        x2 = min(1.0, x1 + 0.01)
    if y2 <= y1:
        y2 = min(1.0, y1 + 0.01)

    left = base.left + int(base.width * x1)
    top = base.top + int(base.height * y1)
    right = base.left + int(base.width * x2)
    bottom = base.top + int(base.height * y2)
    return Rect(left, top, max(1, right - left), max(1, bottom - top))


def compute_scale_info(config: dict[str, Any], capture_rect: Rect) -> ScaleInfo:
    scaling_cfg = config.get("scaling", {})
    ref_w = max(1, int(scaling_cfg.get("reference_width", 1919)))
    ref_h = max(1, int(scaling_cfg.get("reference_height", 1079)))
    scale_x = capture_rect.width / float(ref_w)
    scale_y = capture_rect.height / float(ref_h)
    if bool(scaling_cfg.get("enabled", True)):
        pixel_scale = math.sqrt(max(0.0001, scale_x * scale_y))
        pixel_scale = max(
            float(scaling_cfg.get("min_scale", 0.50)),
            min(float(scaling_cfg.get("max_scale", 1.60)), pixel_scale),
        )
    else:
        pixel_scale = 1.0
    return ScaleInfo(ref_w, ref_h, capture_rect.width, capture_rect.height, scale_x, scale_y, pixel_scale)


def set_runtime_scale(config: dict[str, Any], capture_rect: Rect) -> ScaleInfo:
    scale_info = compute_scale_info(config, capture_rect)
    config["_runtime_scale"] = scale_info.to_dict()
    return scale_info


def runtime_pixel_scale(config: dict[str, Any]) -> float:
    try:
        return float(config.get("_runtime_scale", {}).get("pixel_scale", 1.0))
    except (TypeError, ValueError):
        return 1.0


def scale_int(value: int | float, scale: float, *, minimum: int = 1) -> int:
    return max(minimum, int(round(float(value) * scale)))


def scale_floor(value: int | float, scale: float, *, minimum: int = 1) -> int:
    return max(minimum, int(math.floor(float(value) * scale)))


def scale_ceil(value: int | float, scale: float, *, minimum: int = 1) -> int:
    return max(minimum, int(math.ceil(float(value) * scale)))


def grab_bgr(sct: mss.mss, rect: Rect) -> np.ndarray:
    # mss returns BGRA on Windows. Dropping alpha leaves OpenCV-ready BGR.
    frame = np.asarray(sct.grab(rect.to_mss()))
    return frame[:, :, :3].copy()


def crop_bgr(bgr: np.ndarray, rect: Rect) -> np.ndarray:
    height, width = bgr.shape[:2]
    left = max(0, min(width - 1, rect.left))
    top = max(0, min(height - 1, rect.top))
    right = max(left + 1, min(width, rect.right))
    bottom = max(top + 1, min(height, rect.bottom))
    return bgr[top:bottom, left:right].copy()
