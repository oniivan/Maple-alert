from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np

from vision_core import DetectionResult, Rect, crop_bgr, runtime_pixel_scale, scale_int


_TEMPLATE_CACHE: dict[str, np.ndarray | None] = {}


def _resolve_path(config: dict[str, Any], raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = Path(str(config.get("_config_dir", "."))) / path
    return path


def _load_template(config: dict[str, Any], raw_path: str) -> tuple[np.ndarray | None, str]:
    path = _resolve_path(config, raw_path)
    key = str(path.resolve())
    if key not in _TEMPLATE_CACHE:
        image = cv2.imread(key, cv2.IMREAD_COLOR)
        _TEMPLATE_CACHE[key] = image if image is not None and image.size else None
    return _TEMPLATE_CACHE[key], key


def detect_free_market_title(bgr: np.ndarray, config: dict[str, Any]) -> DetectionResult:
    title_cfg = config["detection"].get("free_market", {})
    if not bool(title_cfg.get("enabled", True)):
        return DetectionResult(False, 0.0, {"enabled": False, "reason": "disabled"})

    raw_template = str(title_cfg.get("template_path", "")).strip()
    if not raw_template:
        return DetectionResult(False, 0.0, {"enabled": True, "reason": "missing_template_path"})

    template, template_path = _load_template(config, raw_template)
    if template is None:
        return DetectionResult(
            False,
            0.0,
            {"enabled": True, "reason": "template_unreadable", "template_path": template_path},
        )

    pixel_scale = runtime_pixel_scale(config)
    search_w = min(scale_int(title_cfg.get("search_width", 560), pixel_scale), bgr.shape[1])
    search_h = min(scale_int(title_cfg.get("search_height", 70), pixel_scale), bgr.shape[0])
    search = crop_bgr(bgr, Rect(0, 0, search_w, search_h))
    search_gray = cv2.cvtColor(search, cv2.COLOR_BGR2GRAY)
    template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

    scale_min = float(title_cfg.get("scale_min", 0.85)) * pixel_scale
    scale_max = float(title_cfg.get("scale_max", 1.20)) * pixel_scale
    steps = max(1, int(title_cfg.get("scale_steps", 15)))
    if scale_max < scale_min:
        scale_min, scale_max = scale_max, scale_min
    scales = np.linspace(scale_min, scale_max, steps)

    best_score = -1.0
    best_box: list[int] | None = None
    best_scale = 0.0
    templ_h, templ_w = template_gray.shape[:2]
    for scale in scales:
        width = max(8, int(round(templ_w * float(scale))))
        height = max(8, int(round(templ_h * float(scale))))
        if width > search_gray.shape[1] or height > search_gray.shape[0]:
            continue
        resized = cv2.resize(template_gray, (width, height), interpolation=cv2.INTER_AREA)
        result = cv2.matchTemplate(search_gray, resized, cv2.TM_CCOEFF_NORMED)
        _, max_value, _, max_location = cv2.minMaxLoc(result)
        if float(max_value) > best_score:
            best_score = float(max_value)
            best_scale = float(scale)
            best_box = [int(max_location[0]), int(max_location[1]), width, height]

    threshold = float(title_cfg.get("threshold", 0.90))
    detected = best_score >= threshold
    info = {
        "enabled": True,
        "template_path": template_path,
        "score": round(max(0.0, best_score), 4),
        "threshold": threshold,
        "scale": round(best_scale, 4),
        "box": best_box,
        "search_size": [int(search_w), int(search_h)],
        "runtime_pixel_scale": round(pixel_scale, 4),
    }
    if not detected:
        info["reason"] = "score_below_threshold"
    return DetectionResult(detected, max(0.0, best_score), info)
