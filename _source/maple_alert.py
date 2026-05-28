from __future__ import annotations

import argparse
import copy
import ctypes
import io
import json
import logging
import math
import os
import re
import subprocess
import sys
import threading
import time
import uuid
import wave
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import mss
import numpy as np

from detectors.minimap_red import detect_minimap_red, locate_minimap_content_rect
from vision_core import (
    DetectionResult,
    Rect,
    ScaleInfo,
    clamp01,
    compute_scale_info,
    crop_bgr,
    grab_bgr,
    roi_to_rect,
    runtime_pixel_scale,
    scale_ceil,
    scale_floor,
    scale_int,
    set_runtime_scale,
)

APP_NAME = "Maple Alert"
APP_VERSION = "0.4.0"
RELEASE_MANIFEST_NAME = "release_manifest.json"
SYSTEM_VOLUME_WARNING_PERCENT = 70
OVERLAY_WIDTH = 340
OVERLAY_HEALTH_HEIGHT = 34
OVERLAY_FULL_HEIGHT = 92
OVERLAY_COLLAPSED_HEIGHT = OVERLAY_HEALTH_HEIGHT
OVERLAY_PLAYER_VOLUME_LABEL = "PLAYER DETECT VOLUME"
OVERLAY_LIE_VOLUME_LABEL = "LIE DETECT VOLUME"
ALERT_VOLUME_KEYS = {
    "captcha": "lie_detect_volume_percent",
    "minimap_red": "player_detected_volume_percent",
}
SENSITIVE_KEY_FRAGMENTS = (
    "token",
    "secret",
    "password",
    "webhook",
    "chat_id",
    "user_id",
    "authorization",
)
REDACTED_VALUE = "<set, redacted>"

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 fallback.
    import tomli as tomllib


DEFAULT_CONFIG: dict[str, Any] = {
    "capture": {
        "window_title": "Maple",
        "ignored_window_title_substrings": [
            "Maple Alert",
            "Maple Alert Health",
            "Maple-alert",
            "File Explorer",
            "Google Chrome",
            "Microsoft Edge",
            "Mozilla Firefox",
            "Brave",
            "Windows PowerShell",
            "PowerShell",
            "Command Prompt",
            "cmd.exe",
            "Terminal",
            "Visual Studio Code",
            "Codex",
        ],
        "target_window": True,
        "monitor_index": 1,
        "fps": 0.25,
        "relocate_window_seconds": 2.0,
    },
    "roi": {
        "captcha": {"x1": 0.25, "y1": 0.25, "x2": 0.75, "y2": 0.75},
        "minimap": {"x1": 0.0, "y1": 0.0, "x2": 0.2398, "y2": 0.3893},
    },
    "scaling": {
        "enabled": True,
        "reference_width": 1919,
        "reference_height": 1079,
        "min_scale": 0.50,
        "max_scale": 1.60,
    },
    "detection": {
        "captcha": {
            "use_template": True,
            "template_path": "",
            "template_threshold": 0.82,
            "template_scale_min": 0.75,
            "template_scale_max": 1.25,
            "template_scale_steps": 11,
            "use_heuristic": True,
            "confidence_threshold": 0.90,
            "patch_width": 145,
            "patch_height": 100,
            "patch_scale_min": 0.94,
            "patch_scale_max": 1.06,
            "patch_scale_steps": 5,
            "patch_blue_hue_min": 101,
            "patch_blue_hue_max": 110,
            "patch_blue_saturation_min": 90,
            "patch_blue_value_min": 100,
            "patch_blue_value_max": 215,
            "patch_blue_fill_min": 0.82,
            "patch_lower_blue_y_min": 0.45,
            "patch_lower_blue_fill_min": 0.94,
            "patch_dark_value_max": 95,
            "patch_dark_region_x1": 0.55,
            "patch_dark_region_y1": 0.00,
            "patch_dark_region_x2": 1.00,
            "patch_dark_region_y2": 0.45,
            "patch_dark_fill_min": 0.33,
            "patch_dark_fill_max": 0.52,
            "patch_blue_h_mean_min": 104.0,
            "patch_blue_h_mean_max": 106.5,
            "patch_blue_s_mean_min": 148.0,
            "patch_blue_s_mean_max": 162.0,
            "patch_blue_v_mean_min": 178.0,
            "patch_blue_v_mean_max": 194.0,
            "patch_blue_h_std_max": 2.5,
            "patch_blue_s_std_max": 12.0,
            "patch_blue_v_std_max": 16.0,
        },
        "minimap": {
            "enabled": True,
            "red_hue_max": 8,
            "red_hue_wrap_min": 174,
            "saturation_min": 220,
            "value_min": 120,
            "dot_width_min": 8,
            "dot_width_max": 13,
            "dot_height_min": 8,
            "dot_height_max": 13,
            "dot_area_min": 42.0,
            "dot_area_max": 85.0,
            "dot_circularity_min": 0.85,
            "dot_extent_min": 0.53,
            "dot_pixel_count_min": 50,
            "dot_mean_saturation_min": 240,
            "dot_mean_value_min": 220,
        },
    },
    "alerts": {
        "safe_mode": True,
        "audible": True,
        "telegram_enabled": True,
        "sound_multiplier": 2,
        "alert_volume_percent": 200,
        "lie_detect_volume_percent": 200,
        "player_detected_volume_percent": 200,
        "alert_settings_file": "runtime/alert_settings.json",
        "captcha_repeat_seconds": 30,
        "minimap_required_seconds": 20,
        "minimap_repeat_seconds": 30,
        "detection_log_interval_seconds": 5,
        "status_interval_seconds": 15,
    },
    "telegram": {"bot_token": "", "chat_id": ""},
    "discord": {
        "enabled": False,
        "bot_token": "",
        "user_id": "",
        "webhook_url": "",
    },
    "notifications": {
        "settings_file": "runtime/notification_settings.json",
        "remote_enabled": False,
    },
    "watchdog": {
        "heartbeat_file": "runtime/heartbeat.json",
        "watchdog_heartbeat_file": "runtime/watchdog_heartbeat.json",
        "supervisor_heartbeat_file": "runtime/supervisor_heartbeat.json",
        "quit_file": "runtime/quit_requested.json",
        "heartbeat_interval_seconds": 2,
        "stale_seconds": 12,
        "check_interval_seconds": 2,
        "restart_delay_seconds": 3,
        "startup_grace_seconds": 15,
        "crash_window_seconds": 300,
        "crash_alert_count": 3,
        "monitor_down_alert_seconds": 120,
        "watchdog_realert_seconds": 120,
        "healthy_clear_seconds": 600,
    },
    "overlay": {
        "enabled": True,
        "x": 320,
        "y": 48,
        "opacity": 0.86,
        "update_interval_ms": 250,
        "warning_seconds": 6,
        "stale_seconds": 14,
        "font_size": 10,
    },
    "debug": {
        "enabled": False,
        "show_windows": False,
        "save_crops": False,
        "crop_dir": "debug_crops",
        "save_blue_block_crops": True,
        "blue_block_crop_dir": "debug_crops/blue_blocks",
        "blue_block_crop_size": 180,
        "blue_block_crop_limit": 10,
        "save_red_dot_crops": True,
        "red_dot_crop_dir": "debug_crops/red_dots",
        "red_dot_crop_size": 100,
        "red_dot_crop_limit": 10,
        "log_file": "logs/detections.log",
    },
}


def capture_interval_seconds(config: dict[str, Any]) -> float:
    raw_fps = config.get("capture", {}).get("fps", DEFAULT_CONFIG["capture"]["fps"])
    try:
        fps = float(raw_fps)
    except (TypeError, ValueError):
        fps = float(DEFAULT_CONFIG["capture"]["fps"])
    # Allow very low polling rates for low CPU use, while avoiding accidental
    # near-infinite sleeps from zero or negative values.
    return 1.0 / max(0.05, fps)


def format_last_seen_minutes(last_seen_epoch: float | int | None, now_epoch: float | None = None) -> str:
    if last_seen_epoch is None:
        return "CLEAR"
    try:
        seen = float(last_seen_epoch)
    except (TypeError, ValueError):
        return "CLEAR"
    if seen <= 0:
        return "CLEAR"
    now = time.time() if now_epoch is None else float(now_epoch)
    minutes = max(0, int((now - seen) // 60))
    return f"{minutes}m ago"


def overlay_live_status_text(
    alert_status: dict[str, Any] | None,
    spin: str,
    now_epoch: float | None = None,
) -> str:
    status = alert_status if isinstance(alert_status, dict) else {}
    parts: list[str] = []
    lie_text = format_last_seen_minutes(status.get("lie_last_seen_epoch"), now_epoch)
    player_text = format_last_seen_minutes(status.get("player_last_seen_epoch"), now_epoch)
    if lie_text != "CLEAR":
        parts.append(f"LIE {lie_text}")
    if player_text != "CLEAR":
        parts.append(f"PLAYER {player_text}")
    if parts:
        return f"LIVE | {' '.join(parts)} {spin}"
    return f"LIVE {spin}"


def minutes_label(seconds: float | int) -> str:
    minutes = max(1, int(round(float(seconds) / 60.0)))
    return f"{minutes} MINS" if minutes != 1 else "1 MIN"


def watchdog_health_title(snapshot: dict[str, Any]) -> str:
    subject = str(snapshot.get("subject", "MONITOR")).strip().upper() or "MONITOR"
    title = str(snapshot.get("title", "")).strip()
    if title:
        return title
    reason = snapshot.get("reason")
    if reason == "monitor_down":
        return f"{subject} DOWN"
    if reason == "crash_loop":
        count = int(snapshot.get("crash_count_window", 0) or 0)
        window = minutes_label(float(snapshot.get("window_seconds", 300) or 300))
        return f"{subject} CRASHED {count} TIMES IN {window}"
    return ""


def overlay_watchdog_health_text(snapshot: dict[str, Any] | None, spin: str) -> str:
    title = watchdog_health_title(snapshot if isinstance(snapshot, dict) else {})
    if title:
        return f"{title} {spin}"
    return f"MONITOR HEALTH ALERT {spin}"


def overlay_drawer_target_height(minimized: bool) -> int:
    return OVERLAY_COLLAPSED_HEIGHT if minimized else OVERLAY_FULL_HEIGHT


def blend_hex_color(foreground: str, background: str, background_amount: float) -> str:
    amount = max(0.0, min(1.0, float(background_amount)))

    def parse(value: str) -> tuple[int, int, int]:
        clean = value.strip().lstrip("#")
        if len(clean) != 6:
            raise ValueError(f"expected #RRGGBB color, got {value!r}")
        return int(clean[0:2], 16), int(clean[2:4], 16), int(clean[4:6], 16)

    fg = parse(foreground)
    bg = parse(background)
    channels = [
        int(round((fg[i] * (1.0 - amount)) + (bg[i] * amount)))
        for i in range(3)
    ]
    return "#" + "".join(f"{channel:02x}" for channel in channels)


def overlay_control_layout() -> dict[str, Any]:
    return {
        "width": OVERLAY_WIDTH,
        "health_height": OVERLAY_HEALTH_HEIGHT,
        "full_height": OVERLAY_FULL_HEIGHT,
        "collapsed_height": OVERLAY_COLLAPSED_HEIGHT,
        "notify_button": (270, 5, 296, 21),
        "quit_button": (320, 5, 336, 21),
        "minimize_button": {
            "box": (300, 5, 316, 21),
            "label_expanded": "-",
            "label_collapsed": "v",
        },
        "volume_warning": {
            "bg": (6, 39, 334, 55),
            "text": (12, 47),
            "button": (286, 39, 334, 55),
            "button_text": (310, 47),
        },
        "test_button": (8, 63, 58, 86),
        "meters": {
            "captcha": {
                "label": OVERLAY_LIE_VOLUME_LABEL,
                "label_pos": (66, 62),
                "outline": (66, 69, 196, 85),
                "fill": (67, 70, 67, 84),
                "text": (131, 77),
                "fill_left": 67,
                "fill_top": 70,
                "fill_bottom": 84,
                "fill_width": 128,
            },
            "minimap_red": {
                "label": OVERLAY_PLAYER_VOLUME_LABEL,
                "label_pos": (204, 62),
                "outline": (204, 69, 334, 85),
                "fill": (205, 70, 205, 84),
                "text": (269, 77),
                "fill_left": 205,
                "fill_top": 70,
                "fill_bottom": 84,
                "fill_width": 128,
            },
        },
    }


@dataclass(frozen=True)
class SystemVolumeState:
    percent: int | None
    muted: bool | None
    error: str | None = None

    @property
    def needs_attention(self) -> bool:
        if self.muted is True:
            return True
        if self.percent is not None and self.percent < SYSTEM_VOLUME_WARNING_PERCENT:
            return True
        return False


class WatchdogFailureTracker:
    def __init__(self, config: dict[str, Any], subject: str = "MONITOR") -> None:
        watchdog_cfg = config.get("watchdog", {})
        self.subject = subject.strip().upper() or "MONITOR"
        self.window_seconds = max(30.0, float(watchdog_cfg.get("crash_window_seconds", 300)))
        self.crash_alert_count = max(1, int(watchdog_cfg.get("crash_alert_count", 3)))
        self.monitor_down_alert_seconds = max(
            10.0,
            float(watchdog_cfg.get("monitor_down_alert_seconds", 120)),
        )
        self.realert_seconds = max(10.0, float(watchdog_cfg.get("watchdog_realert_seconds", 120)))
        self.healthy_clear_seconds = max(10.0, float(watchdog_cfg.get("healthy_clear_seconds", 600)))
        self.events: list[dict[str, Any]] = []
        self.monitor_unavailable_since: float | None = None
        self.unhealthy_since: float | None = None
        self.healthy_since: float | None = None
        self.latched_title = ""
        self.latched_reason = ""
        self.last_sound_at: float | None = None

    def record_abnormal(self, reason: str, now: float | None = None, exit_code: int | None = None) -> None:
        timestamp = time.time() if now is None else float(now)
        event = {
            "epoch_seconds": timestamp,
            "reason": reason,
        }
        if exit_code is not None:
            event["exit_code"] = int(exit_code)
        self.events.append(event)
        self.healthy_since = None
        if self.monitor_unavailable_since is None:
            self.monitor_unavailable_since = timestamp

    def _prune(self, now: float) -> list[dict[str, Any]]:
        cutoff = now - self.window_seconds
        self.events = [
            event
            for event in self.events
            if float(event.get("epoch_seconds", 0.0)) >= cutoff
        ]
        return self.events

    def update(self, monitor_available: bool, now: float | None = None) -> dict[str, Any]:
        timestamp = time.time() if now is None else float(now)
        events = self._prune(timestamp)

        if monitor_available:
            self.monitor_unavailable_since = None
        elif self.monitor_unavailable_since is None:
            self.monitor_unavailable_since = timestamp

        down_seconds = (
            0.0
            if self.monitor_unavailable_since is None
            else max(0.0, timestamp - self.monitor_unavailable_since)
        )
        crash_count = len(events)
        raw_reason = ""
        raw_title = ""
        if crash_count >= self.crash_alert_count:
            raw_reason = "crash_loop"
            raw_title = (
                f"{self.subject} CRASHED {crash_count} TIMES IN "
                f"{minutes_label(self.window_seconds)}"
            )
        elif down_seconds >= self.monitor_down_alert_seconds:
            raw_reason = "monitor_down"
            raw_title = f"{self.subject} DOWN {max(1, int(down_seconds // 60))}m+"

        raw_active = bool(raw_reason)
        latched = False
        if raw_active:
            self.unhealthy_since = self.unhealthy_since or timestamp
            self.healthy_since = None
            self.latched_title = raw_title
            self.latched_reason = raw_reason
        elif self.unhealthy_since is not None:
            if monitor_available:
                self.healthy_since = self.healthy_since or timestamp
                if timestamp - self.healthy_since >= self.healthy_clear_seconds:
                    self.unhealthy_since = None
                    self.healthy_since = None
                    self.latched_title = ""
                    self.latched_reason = ""
                else:
                    latched = True
            else:
                self.healthy_since = None
                latched = True

        active = raw_active or latched
        reason = raw_reason or (self.latched_reason if latched else "")
        title = raw_title or (self.latched_title if latched else "")
        return {
            "active": active,
            "subject": self.subject,
            "soundable": raw_active,
            "latched": latched,
            "reason": reason,
            "title": title,
            "crash_count_window": crash_count,
            "crash_alert_count": self.crash_alert_count,
            "window_seconds": self.window_seconds,
            "monitor_down_seconds": round(down_seconds, 1),
            "monitor_down_alert_seconds": self.monitor_down_alert_seconds,
            "unhealthy_since": self.unhealthy_since,
            "healthy_since": self.healthy_since,
            "recent_events": events[-5:],
        }

    def should_sound(self, snapshot: dict[str, Any], now: float | None = None) -> bool:
        if not bool(snapshot.get("active", False)):
            return False
        if not bool(snapshot.get("soundable", False)):
            return False
        timestamp = time.time() if now is None else float(now)
        if self.last_sound_at is None:
            return True
        return timestamp - self.last_sound_at >= self.realert_seconds

    def mark_sounded(self, now: float | None = None) -> None:
        self.last_sound_at = time.time() if now is None else float(now)


def system_volume_button_state(warning_active: bool, ignored: bool, pulse_on: bool) -> dict[str, Any]:
    if not warning_active:
        return {
            "visible": False,
            "label": "",
            "fill": "#1b2430",
            "outline": "#3b4654",
            "label_fill": "#aab4c0",
        }

    if ignored:
        return {
            "visible": True,
            "label": "WARN",
            "fill": "#3a2f0f" if pulse_on else "#1b2430",
            "outline": "#ffd43b",
            "label_fill": "#fff2b0",
        }

    return {
        "visible": True,
        "label": "IGNORE",
        "fill": "#3a2f0f" if pulse_on else "#1b2430",
        "outline": "#ffd43b",
        "label_fill": "#fff2b0",
    }


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path: Path) -> dict[str, Any]:
    loaded_files: list[str] = []
    if path.exists():
        with path.open("rb") as fh:
            file_config = tomllib.load(fh)
        config = deep_merge(DEFAULT_CONFIG, file_config)
        loaded_files.append(str(path.resolve()))
    else:
        config = copy.deepcopy(DEFAULT_CONFIG)

    local_path = path.with_name(f"{path.stem}.local{path.suffix}")
    if local_path.exists() and local_path.resolve() != path.resolve():
        with local_path.open("rb") as fh:
            local_config = tomllib.load(fh)
        config = deep_merge(config, local_config)
        loaded_files.append(str(local_path.resolve()))

    # Environment variables make the checked-in config safe to share.
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if token:
        config["telegram"]["bot_token"] = token
    if chat_id:
        config["telegram"]["chat_id"] = chat_id
    discord_token = os.getenv("DISCORD_BOT_TOKEN")
    discord_user_id = os.getenv("DISCORD_USER_ID")
    discord_webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if discord_token:
        config["discord"]["bot_token"] = discord_token
    if discord_user_id:
        config["discord"]["user_id"] = discord_user_id
    if discord_webhook_url:
        config["discord"]["webhook_url"] = discord_webhook_url

    config["_config_dir"] = str(path.resolve().parent)
    config["_loaded_config_files"] = loaded_files
    return config


def resolve_config_path(config: dict[str, Any], value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path(config["_config_dir"]) / path
    return path


def quit_signal_path(config: dict[str, Any]) -> Path:
    return resolve_config_path(
        config,
        str(config["watchdog"].get("quit_file", "runtime/quit_requested.json")),
    )


def request_quit(config: dict[str, Any], source: str) -> Path:
    path = quit_signal_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "epoch_seconds": time.time(),
        "pid": os.getpid(),
        "source": source,
    }
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    temp_path.replace(path)
    return path


def quit_requested(config: dict[str, Any], started_at_epoch: float) -> bool:
    path = quit_signal_path(config)
    try:
        return path.exists() and path.stat().st_mtime >= started_at_epoch
    except OSError:
        return False


def alert_settings_path(config: dict[str, Any]) -> Path:
    return resolve_config_path(
        config,
        str(config["alerts"].get("alert_settings_file", "runtime/alert_settings.json")),
    )


def read_alert_settings_payload(config: dict[str, Any]) -> dict[str, Any]:
    path = alert_settings_path(config)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def write_alert_settings_payload(config: dict[str, Any], payload: dict[str, Any]) -> None:
    path = alert_settings_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    updated_payload = dict(payload)
    updated_payload["updated_at"] = datetime.now().isoformat(timespec="seconds")
    updated_payload["pid"] = os.getpid()
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(updated_payload, sort_keys=True), encoding="utf-8")
    temp_path.replace(path)


def clamp_alert_volume_percent(value: Any, fallback: int = 200) -> int:
    try:
        if value is None:
            raise ValueError("missing volume")
        raw_value = value
        return max(0, min(250, int(round(float(raw_value)))))
    except Exception:
        return max(0, min(250, int(round(float(fallback)))))


def alert_volume_key_for_kind(kind: str | None = None) -> str:
    if kind is None:
        return "alert_volume_percent"
    return ALERT_VOLUME_KEYS.get(kind, "alert_volume_percent")


def default_alert_volume_percent(config: dict[str, Any], kind: str | None = None) -> int:
    alerts_cfg = config["alerts"]
    key = alert_volume_key_for_kind(kind)
    raw_value = alerts_cfg.get(key)
    if raw_value is not None:
        return clamp_alert_volume_percent(raw_value)
    if alerts_cfg.get("alert_volume_percent") is not None:
        raw_value = alerts_cfg.get("alert_volume_percent", 200)
    else:
        raw_value = float(alerts_cfg.get("sound_multiplier", 2)) * 100
    return clamp_alert_volume_percent(raw_value)


def read_alert_volume_percent(config: dict[str, Any], kind: str | None = None) -> int:
    payload = read_alert_settings_payload(config)
    key = alert_volume_key_for_kind(kind)
    if key in payload:
        return clamp_alert_volume_percent(payload.get(key), default_alert_volume_percent(config, kind))
    if kind is not None and "alert_volume_percent" in payload:
        return clamp_alert_volume_percent(payload.get("alert_volume_percent"), default_alert_volume_percent(config, kind))
    return default_alert_volume_percent(config, kind)


def write_alert_volume_percent(config: dict[str, Any], percent: int, kind: str | None = None) -> None:
    payload = read_alert_settings_payload(config)
    value = clamp_alert_volume_percent(percent)
    payload[alert_volume_key_for_kind(kind)] = value
    write_alert_settings_payload(config, payload)


def read_ignore_system_volume_warning(config: dict[str, Any]) -> bool:
    return bool(read_alert_settings_payload(config).get("ignore_system_volume_warning", False))


def write_ignore_system_volume_warning(config: dict[str, Any], ignore: bool) -> None:
    payload = read_alert_settings_payload(config)
    payload["ignore_system_volume_warning"] = bool(ignore)
    write_alert_settings_payload(config, payload)


def notification_settings_path(config: dict[str, Any]) -> Path:
    return resolve_config_path(
        config,
        str(config.get("notifications", {}).get("settings_file", "runtime/notification_settings.json")),
    )


def read_notification_settings(config: dict[str, Any]) -> dict[str, Any]:
    path = notification_settings_path(config)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def write_notification_settings(config: dict[str, Any], payload: dict[str, Any]) -> None:
    path = notification_settings_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    updated_payload = dict(payload)
    updated_payload["updated_at"] = datetime.now().isoformat(timespec="seconds")
    updated_payload["pid"] = os.getpid()
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(updated_payload, sort_keys=True), encoding="utf-8")
    temp_path.replace(path)


def _runtime_service_settings(config: dict[str, Any], service: str) -> dict[str, Any]:
    settings = read_notification_settings(config)
    service_settings = settings.get(service, {})
    return service_settings if isinstance(service_settings, dict) else {}


def notification_value(config: dict[str, Any], service: str, key: str) -> str:
    runtime_value = _runtime_service_settings(config, service).get(key)
    if runtime_value is not None:
        return str(runtime_value).strip()
    return str(config.get(service, {}).get(key, "")).strip()


def remote_notifications_enabled(config: dict[str, Any]) -> bool:
    settings = read_notification_settings(config)
    if "remote_enabled" in settings:
        return bool(settings.get("remote_enabled"))
    notifications_cfg = config.get("notifications", {})
    return bool(notifications_cfg.get("remote_enabled", False)) or not bool(
        config.get("alerts", {}).get("safe_mode", True)
    )


def notification_service_enabled(config: dict[str, Any], service: str) -> bool:
    if not remote_notifications_enabled(config):
        return False
    runtime_settings = _runtime_service_settings(config, service)
    service_cfg = config.get(service, {})
    if service == "telegram":
        if "enabled" in runtime_settings:
            enabled = bool(runtime_settings.get("enabled"))
        else:
            enabled = bool(
                service_cfg.get("enabled", False)
                or config.get("alerts", {}).get("telegram_enabled", False)
            )
        return enabled and bool(notification_value(config, "telegram", "bot_token")) and bool(
            notification_value(config, "telegram", "chat_id")
        )
    if service == "discord":
        enabled = bool(runtime_settings.get("enabled", service_cfg.get("enabled", False)))
        has_webhook = bool(notification_value(config, "discord", "webhook_url"))
        has_dm = bool(notification_value(config, "discord", "bot_token")) and bool(
            notification_value(config, "discord", "user_id")
        )
        return enabled and (has_webhook or has_dm)
    return False


def send_telegram_notification(
    config: dict[str, Any],
    logger: logging.Logger,
    message: str,
    post_func: Any | None = None,
) -> bool:
    if not notification_service_enabled(config, "telegram"):
        logger.info("Telegram skipped because notifications are disabled or token/chat_id are not configured")
        return False

    token = notification_value(config, "telegram", "bot_token")
    chat_id = notification_value(config, "telegram", "chat_id")
    try:
        if post_func is None:
            import requests

            post_func = requests.post

        response = post_func(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": message},
            timeout=8,
        )
        response.raise_for_status()
        logger.info("Telegram message sent")
        return True
    except Exception as exc:
        logger.warning("Telegram send failed: %s", exc)
        return False


def send_discord_notification(
    config: dict[str, Any],
    logger: logging.Logger,
    message: str,
    post_func: Any | None = None,
) -> bool:
    if not notification_service_enabled(config, "discord"):
        logger.info("Discord skipped because notifications are disabled or credentials are not configured")
        return False

    try:
        if post_func is None:
            import requests

            post_func = requests.post

        webhook_url = notification_value(config, "discord", "webhook_url")
        if webhook_url:
            response = post_func(webhook_url, json={"content": message}, timeout=8)
            response.raise_for_status()
            logger.info("Discord webhook message sent")
            return True

        token = notification_value(config, "discord", "bot_token")
        user_id = notification_value(config, "discord", "user_id")
        headers = {
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
        }
        dm_response = post_func(
            "https://discord.com/api/v10/users/@me/channels",
            headers=headers,
            json={"recipient_id": user_id},
            timeout=8,
        )
        dm_response.raise_for_status()
        channel_id = str(dm_response.json().get("id", "")).strip()
        if not channel_id:
            raise RuntimeError("Discord did not return a DM channel id")
        message_response = post_func(
            f"https://discord.com/api/v10/channels/{channel_id}/messages",
            headers=headers,
            json={"content": message},
            timeout=8,
        )
        message_response.raise_for_status()
        logger.info("Discord DM message sent")
        return True
    except Exception as exc:
        logger.warning("Discord send failed: %s", exc)
        return False


def send_remote_notifications(config: dict[str, Any], logger: logging.Logger, message: str) -> None:
    send_telegram_notification(config, logger, message)
    send_discord_notification(config, logger, message)


def setup_logging(config: dict[str, Any]) -> logging.Logger:
    log_file = resolve_config_path(config, config["debug"]["log_file"])
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("maple_alert")
    logger.setLevel(logging.DEBUG if config["debug"]["enabled"] else logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)
    logger.addHandler(console_handler)
    return logger


def list_windows() -> list[tuple[str, Rect]]:
    found: list[tuple[str, Rect]] = []

    try:
        import pygetwindow as gw

        for window in gw.getAllWindows():
            title = window.title.strip()
            if not title or window.width <= 0 or window.height <= 0:
                continue
            if getattr(window, "isMinimized", False):
                continue
            found.append((title, Rect(window.left, window.top, window.width, window.height)))
        if found:
            return found
    except Exception:
        pass

    try:
        import win32gui

        def enum_handler(hwnd: int, _: Any) -> None:
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd).strip()
            if not title:
                return
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            width = right - left
            height = bottom - top
            if width > 0 and height > 0:
                found.append((title, Rect(left, top, width, height)))

        win32gui.EnumWindows(enum_handler, None)
    except Exception:
        pass

    return found


def ignored_window_title_substrings(capture_cfg: dict[str, Any]) -> list[str]:
    raw_ignored = capture_cfg.get(
        "ignored_window_title_substrings",
        DEFAULT_CONFIG["capture"]["ignored_window_title_substrings"],
    )
    if isinstance(raw_ignored, str):
        raw_ignored = [raw_ignored]
    if not isinstance(raw_ignored, list):
        raw_ignored = DEFAULT_CONFIG["capture"]["ignored_window_title_substrings"]
    return [
        str(fragment).casefold().strip()
        for fragment in raw_ignored
        if str(fragment).strip()
    ]


def is_ignored_window_title(title: str, ignored_fragments: list[str]) -> bool:
    folded_title = title.casefold().strip()
    return any(fragment in folded_title for fragment in ignored_fragments)


def find_window_rect(title_substring: str, ignored_titles: list[str] | None = None) -> Rect | None:
    needle = title_substring.casefold().strip()
    if not needle:
        return None
    ignored = (
        ignored_titles
        if ignored_titles is not None
        else ignored_window_title_substrings(DEFAULT_CONFIG["capture"])
    )
    for title, rect in list_windows():
        if is_ignored_window_title(title, ignored):
            continue
        if needle in title.casefold():
            return rect
    return None


def get_monitor_rect(sct: mss.mss, monitor_index: int) -> Rect:
    monitors = sct.monitors
    index = monitor_index
    if index < 0 or index >= len(monitors):
        index = 1 if len(monitors) > 1 else 0
    monitor = monitors[index]
    return Rect(
        int(monitor["left"]),
        int(monitor["top"]),
        int(monitor["width"]),
        int(monitor["height"]),
    )


def resolve_capture_rect(sct: mss.mss, config: dict[str, Any]) -> tuple[Rect, str]:
    capture_cfg = config["capture"]
    if capture_cfg["target_window"]:
        window_rect = find_window_rect(
            capture_cfg["window_title"],
            ignored_window_title_substrings(capture_cfg),
        )
        if window_rect:
            return window_rect, "window"

    return get_monitor_rect(sct, int(capture_cfg["monitor_index"])), "monitor"


class CaptchaDetector:
    def __init__(self, config: dict[str, Any], logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger
        self.template_gray: np.ndarray | None = None
        self.template_path = ""
        self._load_template()

    def _load_template(self) -> None:
        cap_cfg = self.config["detection"]["captcha"]
        if not cap_cfg["use_template"]:
            return
        raw_path = str(cap_cfg.get("template_path", "")).strip()
        if not raw_path:
            return

        path = resolve_config_path(self.config, raw_path)
        if not path.exists():
            self.logger.warning("CAPTCHA template not found: %s", path)
            return

        template = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if template is None or template.size == 0:
            self.logger.warning("CAPTCHA template could not be read: %s", path)
            return

        self.template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        self.template_path = str(path)
        self.logger.info("Loaded CAPTCHA template: %s", path)

    def detect(self, bgr: np.ndarray) -> DetectionResult:
        cap_cfg = self.config["detection"]["captcha"]

        template_score = 0.0
        template_info: dict[str, Any] = {}
        if cap_cfg["use_template"] and self.template_gray is not None:
            template_score, template_info = self._template_score(bgr)

        heuristic_score = 0.0
        heuristic_info: dict[str, Any] = {}
        if cap_cfg["use_heuristic"]:
            heuristic_score, heuristic_info = self._heuristic_score(bgr)

        template_detected = (
            cap_cfg["use_template"]
            and self.template_gray is not None
            and template_score >= float(cap_cfg["template_threshold"])
        )
        heuristic_detected = cap_cfg["use_heuristic"] and heuristic_score >= float(
            cap_cfg["confidence_threshold"]
        )
        confidence = max(template_score, heuristic_score)
        detected = bool(template_detected or heuristic_detected)
        info = {
            "template_score": round(template_score, 4),
            "heuristic_score": round(heuristic_score, 4),
            "template_threshold": cap_cfg["template_threshold"],
            "heuristic_threshold": cap_cfg["confidence_threshold"],
            "template": template_info,
            "heuristic": heuristic_info,
        }
        return DetectionResult(detected, confidence, info)

    def _template_score(self, bgr: np.ndarray) -> tuple[float, dict[str, Any]]:
        cap_cfg = self.config["detection"]["captcha"]
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        roi_h, roi_w = gray.shape[:2]
        assert self.template_gray is not None
        templ_h, templ_w = self.template_gray.shape[:2]

        runtime_scale = runtime_pixel_scale(self.config)
        scale_min = float(cap_cfg["template_scale_min"]) * runtime_scale
        scale_max = float(cap_cfg["template_scale_max"]) * runtime_scale
        steps = max(1, int(cap_cfg["template_scale_steps"]))
        scales = np.linspace(scale_min, scale_max, steps)

        best_score = 0.0
        best_box: tuple[int, int, int, int] | None = None
        best_scale = 1.0

        for scale in scales:
            scaled_w = max(1, int(templ_w * scale))
            scaled_h = max(1, int(templ_h * scale))
            if scaled_w > roi_w or scaled_h > roi_h:
                continue

            resized = cv2.resize(
                self.template_gray,
                (scaled_w, scaled_h),
                interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR,
            )
            result = cv2.matchTemplate(gray, resized, cv2.TM_CCOEFF_NORMED)
            _, max_value, _, max_loc = cv2.minMaxLoc(result)
            if max_value > best_score:
                best_score = float(max_value)
                best_scale = float(scale)
                best_box = (int(max_loc[0]), int(max_loc[1]), scaled_w, scaled_h)

        info = {
            "scale": round(best_scale, 3),
            "runtime_pixel_scale": round(runtime_scale, 4),
            "box": best_box,
        }
        return best_score, info

    def _heuristic_score(self, bgr: np.ndarray) -> tuple[float, dict[str, Any]]:
        cap_cfg = self.config["detection"]["captcha"]
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv)
        height, width = bgr.shape[:2]

        # Strict CAPTCHA signal: a blue dialog patch with the lie-detector icon
        # occupying the upper-right part of the patch. This avoids accepting
        # unrelated pure-blue map/UI blocks.
        blue_bool = (
            (h >= int(cap_cfg["patch_blue_hue_min"]))
            & (h <= int(cap_cfg["patch_blue_hue_max"]))
            & (s >= int(cap_cfg["patch_blue_saturation_min"]))
            & (v >= int(cap_cfg["patch_blue_value_min"]))
            & (v <= int(cap_cfg["patch_blue_value_max"]))
        )
        dark_bool = v <= int(cap_cfg["patch_dark_value_max"])
        runtime_scale = runtime_pixel_scale(self.config)
        unscaled_w = max(1, int(cap_cfg["patch_width"]))
        unscaled_h = max(1, int(cap_cfg["patch_height"]))
        base_w = scale_int(unscaled_w, runtime_scale)
        base_h = scale_int(unscaled_h, runtime_scale)
        if base_w > width or base_h > height:
            return 0.0, {
                "method": "blue_patch_with_dark_corner",
                "reason": "roi_smaller_than_patch",
                "roi_size": [width, height],
                "patch_size": [unscaled_w, unscaled_h],
                "scaled_patch_size": [base_w, base_h],
                "runtime_pixel_scale": round(runtime_scale, 4),
            }

        blue_u8 = blue_bool.astype(np.uint8)
        dark_u8 = dark_bool.astype(np.uint8)
        blue_integral = cv2.integral(blue_u8, sdepth=cv2.CV_32S)
        dark_integral = cv2.integral(dark_u8, sdepth=cv2.CV_32S)

        def rect_sums(
            integral: np.ndarray,
            rows: int,
            cols: int,
            offset_x: int,
            offset_y: int,
            rect_w: int,
            rect_h: int,
        ) -> np.ndarray:
            return (
                integral[offset_y + rect_h : offset_y + rect_h + rows, offset_x + rect_w : offset_x + rect_w + cols]
                - integral[offset_y : offset_y + rows, offset_x + rect_w : offset_x + rect_w + cols]
                - integral[offset_y + rect_h : offset_y + rect_h + rows, offset_x : offset_x + cols]
                + integral[offset_y : offset_y + rows, offset_x : offset_x + cols]
            )

        blue_fill_min = float(cap_cfg["patch_blue_fill_min"])
        lower_blue_fill_min = float(cap_cfg["patch_lower_blue_fill_min"])
        lower_y_min = float(cap_cfg["patch_lower_blue_y_min"])
        dark_fill_min = float(cap_cfg["patch_dark_fill_min"])
        dark_fill_max = float(cap_cfg["patch_dark_fill_max"])
        h_mean_min = float(cap_cfg["patch_blue_h_mean_min"])
        h_mean_max = float(cap_cfg["patch_blue_h_mean_max"])
        s_mean_min = float(cap_cfg["patch_blue_s_mean_min"])
        s_mean_max = float(cap_cfg["patch_blue_s_mean_max"])
        v_mean_min = float(cap_cfg["patch_blue_v_mean_min"])
        v_mean_max = float(cap_cfg["patch_blue_v_mean_max"])
        h_std_max = float(cap_cfg["patch_blue_h_std_max"])
        s_std_max = float(cap_cfg["patch_blue_s_std_max"])
        v_std_max = float(cap_cfg["patch_blue_v_std_max"])
        scale_min = float(cap_cfg.get("patch_scale_min", 1.0))
        scale_max = float(cap_cfg.get("patch_scale_max", 1.0))
        scale_steps = max(1, int(cap_cfg.get("patch_scale_steps", 1)))
        max_candidates = 80
        best_info: dict[str, Any] = {
            "method": "blue_patch_with_dark_corner",
            "reason": "no_patch_candidate",
            "patch_size": [unscaled_w, unscaled_h],
            "scaled_patch_size": [base_w, base_h],
            "runtime_pixel_scale": round(runtime_scale, 4),
            "roi_size": [width, height],
            "best_primary_score": 0.0,
        }
        best_failed_score = 0.0

        for raw_scale in np.linspace(scale_min, scale_max, scale_steps):
            patch_w = max(1, int(round(base_w * float(raw_scale))))
            patch_h = max(1, int(round(base_h * float(raw_scale))))
            if patch_w > width or patch_h > height:
                continue

            rows = height - patch_h + 1
            cols = width - patch_w + 1
            patch_area = float(patch_w * patch_h)
            blue_sums = rect_sums(blue_integral, rows, cols, 0, 0, patch_w, patch_h)
            blue_fill = blue_sums / patch_area

            dark_x1 = max(0, min(patch_w - 1, int(round(patch_w * float(cap_cfg["patch_dark_region_x1"])))))
            dark_y1 = max(0, min(patch_h - 1, int(round(patch_h * float(cap_cfg["patch_dark_region_y1"])))))
            dark_x2 = max(dark_x1 + 1, min(patch_w, int(round(patch_w * float(cap_cfg["patch_dark_region_x2"])))))
            dark_y2 = max(dark_y1 + 1, min(patch_h, int(round(patch_h * float(cap_cfg["patch_dark_region_y2"])))))
            dark_w = dark_x2 - dark_x1
            dark_h = dark_y2 - dark_y1
            dark_sums = rect_sums(dark_integral, rows, cols, dark_x1, dark_y1, dark_w, dark_h)
            dark_fill = dark_sums / float(dark_w * dark_h)

            lower_y1 = max(0, min(patch_h - 1, int(round(patch_h * lower_y_min))))
            lower_h = patch_h - lower_y1
            lower_sums = rect_sums(blue_integral, rows, cols, 0, lower_y1, patch_w, lower_h)
            lower_blue_fill = lower_sums / float(patch_w * lower_h)

            primary_valid = (
                (blue_fill >= blue_fill_min)
                & (lower_blue_fill >= lower_blue_fill_min)
                & (dark_fill >= dark_fill_min)
                & (dark_fill <= dark_fill_max)
            )
            primary_score = (
                np.minimum(blue_fill / blue_fill_min, 1.0) * 0.45
                + np.minimum(lower_blue_fill / lower_blue_fill_min, 1.0) * 0.25
                + np.minimum(dark_fill / dark_fill_min, 1.0) * 0.30
            )
            _, max_primary_score, _, max_primary_loc = cv2.minMaxLoc(
                np.where(primary_valid, primary_score, 0.0).astype(np.float32)
            )
            if float(max_primary_score) > float(best_info.get("best_primary_score", 0.0)):
                bx, by = int(max_primary_loc[0]), int(max_primary_loc[1])
                best_info.update(
                    {
                        "best_primary_score": round(float(max_primary_score), 4),
                        "box": [bx, by, patch_w, patch_h],
                        "scale": round(float(raw_scale), 3),
                        "runtime_pixel_scale": round(runtime_scale, 4),
                        "effective_scale": round(float(raw_scale) * runtime_scale, 4),
                        "scaled_patch_size": [patch_w, patch_h],
                        "blue_fill": round(float(blue_fill[by, bx]), 4),
                        "lower_blue_fill": round(float(lower_blue_fill[by, bx]), 4),
                        "dark_fill": round(float(dark_fill[by, bx]), 4),
                    }
                )

            valid_count = int(np.count_nonzero(primary_valid))
            if valid_count == 0:
                continue

            candidate_scores = np.where(primary_valid, primary_score, -1.0).ravel()
            top_n = min(max_candidates, valid_count)
            top_indices = np.argpartition(candidate_scores, -top_n)[-top_n:]
            top_indices = top_indices[np.argsort(candidate_scores[top_indices])[::-1]]

            for flat_index in top_indices:
                y, x = [int(value) for value in np.unravel_index(int(flat_index), primary_valid.shape)]
                patch_hsv = hsv[y : y + patch_h, x : x + patch_w]
                patch_blue = blue_bool[y : y + patch_h, x : x + patch_w]
                blue_pixels = patch_hsv[patch_blue]
                if blue_pixels.size == 0:
                    continue

                h_mean = float(np.mean(blue_pixels[:, 0]))
                s_mean = float(np.mean(blue_pixels[:, 1]))
                v_mean = float(np.mean(blue_pixels[:, 2]))
                h_std = float(np.std(blue_pixels[:, 0]))
                s_std = float(np.std(blue_pixels[:, 1]))
                v_std = float(np.std(blue_pixels[:, 2]))
                mean_ok = (
                    h_mean_min <= h_mean <= h_mean_max
                    and s_mean_min <= s_mean <= s_mean_max
                    and v_mean_min <= v_mean <= v_mean_max
                )
                uniformity_ok = h_std <= h_std_max and s_std <= s_std_max and v_std <= v_std_max
                info = {
                    "method": "blue_patch_with_dark_corner",
                    "box": [x, y, patch_w, patch_h],
                    "patch_size": [unscaled_w, unscaled_h],
                    "scaled_patch_size": [patch_w, patch_h],
                    "scale": round(float(raw_scale), 3),
                    "runtime_pixel_scale": round(runtime_scale, 4),
                    "effective_scale": round(float(raw_scale) * runtime_scale, 4),
                    "roi_size": [width, height],
                    "blue_fill": round(float(blue_fill[y, x]), 4),
                    "lower_blue_fill": round(float(lower_blue_fill[y, x]), 4),
                    "dark_fill": round(float(dark_fill[y, x]), 4),
                    "blue_pixels": int(len(blue_pixels)),
                    "required": {
                        "blue_fill_min": blue_fill_min,
                        "lower_blue_fill_min": lower_blue_fill_min,
                        "dark_fill": [dark_fill_min, dark_fill_max],
                    },
                    "blue_h_mean": round(h_mean, 3),
                    "blue_s_mean": round(s_mean, 3),
                    "blue_v_mean": round(v_mean, 3),
                    "blue_h_std": round(h_std, 3),
                    "blue_s_std": round(s_std, 3),
                    "blue_v_std": round(v_std, 3),
                    "blue_mean_ok": mean_ok,
                    "blue_uniformity_ok": uniformity_ok,
                    "blue_mean_ranges": {
                        "h": [h_mean_min, h_mean_max],
                        "s": [s_mean_min, s_mean_max],
                        "v": [v_mean_min, v_mean_max],
                    },
                    "blue_std_max": {
                        "h": h_std_max,
                        "s": s_std_max,
                        "v": v_std_max,
                    },
                    "blue_hsv_range": {
                        "h": [cap_cfg["patch_blue_hue_min"], cap_cfg["patch_blue_hue_max"]],
                        "s_min": cap_cfg["patch_blue_saturation_min"],
                        "v": [cap_cfg["patch_blue_value_min"], cap_cfg["patch_blue_value_max"]],
                    },
                    "dark_region": [dark_x1, dark_y1, dark_w, dark_h],
                }
                raw_score = float(candidate_scores[flat_index])
                if not uniformity_ok:
                    info["reason"] = "patch_blue_pixels_not_uniform_enough"
                    if raw_score > best_failed_score:
                        best_failed_score = raw_score
                        best_info = info
                    continue
                if not mean_ok:
                    info["reason"] = "patch_blue_pixel_mean_out_of_range"
                    if raw_score > best_failed_score:
                        best_failed_score = raw_score
                        best_info = info
                    continue

                info["reason"] = "patch_match"
                return 1.0, info

        return min(0.89, float(best_info.get("best_primary_score", 0.0))), best_info


class AlertManager:
    def __init__(self, config: dict[str, Any], logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger
        self.last_alert: dict[str, float] = {"captcha": 0.0, "minimap_red": 0.0}
        self.last_detection_log: dict[str, float] = {"captcha": 0.0, "minimap_red": 0.0}
        self.minimap_seen_since: float | None = None
        self.active: dict[str, bool] = {"captcha": False, "minimap_red": False}
        self.last_seen_epoch: dict[str, float | None] = {"captcha": None, "minimap_red": None}

    def handle_result(self, kind: str, result: DetectionResult) -> bool:
        if kind == "captcha":
            return self._handle_captcha(result)
        if kind == "minimap_red":
            return self._handle_minimap_red(result)

        if result.detected:
            self._log_detection(kind, result)
            self._fire_alert(kind, result)
            return True
        return False

    def _handle_captcha(self, result: DetectionResult) -> bool:
        if not result.detected:
            # Reset so a newly reappearing prompt alerts immediately.
            if self.active.get("captcha", False):
                self._print_state_change("captcha", "cleared")
            self.active["captcha"] = False
            self.last_alert["captcha"] = 0.0
            return False

        self.last_seen_epoch["captcha"] = time.time()
        if not self.active.get("captcha", False):
            self.active["captcha"] = True

        now = time.monotonic()
        repeat_seconds = max(0.0, float(self.config["alerts"]["captcha_repeat_seconds"]))
        seconds_since_alert = now - self.last_alert.get("captcha", 0.0)
        next_alert_in = max(0.0, repeat_seconds - seconds_since_alert)

        self._log_detection("captcha", result, {"next_alert_in_seconds": round(next_alert_in, 1)})

        if seconds_since_alert >= repeat_seconds:
            self._fire_alert("captcha", result)
            return True
        return False

    def _handle_minimap_red(self, result: DetectionResult) -> bool:
        now = time.monotonic()
        required_seconds = max(0.0, float(self.config["alerts"]["minimap_required_seconds"]))
        repeat_seconds = max(0.0, float(self.config["alerts"]["minimap_repeat_seconds"]))

        if not result.detected:
            if self.minimap_seen_since is not None:
                present_for = now - self.minimap_seen_since
                self._print_state_change("minimap_red", "cleared", {"present_for_seconds": round(present_for, 1)})
                self.logger.info(
                    "minimap_red cleared after %.1fs; persistence timer reset",
                    present_for,
                )
            self.minimap_seen_since = None
            self.active["minimap_red"] = False
            self.last_alert["minimap_red"] = 0.0
            return False

        self.last_seen_epoch["minimap_red"] = time.time()
        if self.minimap_seen_since is None:
            self.minimap_seen_since = now
            self.active["minimap_red"] = True
            self._print_state_change("minimap_red", "detected", {"required_seconds": required_seconds})
            self.logger.info("minimap_red started; waiting %.1fs before first alert", required_seconds)

        present_for = now - self.minimap_seen_since
        seconds_since_alert = now - self.last_alert.get("minimap_red", 0.0)
        first_alert_pending = self.last_alert.get("minimap_red", 0.0) == 0.0
        ready_for_first_alert = present_for >= required_seconds
        ready_for_repeat_alert = not first_alert_pending and seconds_since_alert >= repeat_seconds

        if first_alert_pending:
            next_alert_in = max(0.0, required_seconds - present_for)
        else:
            next_alert_in = max(0.0, repeat_seconds - seconds_since_alert)

        log_extra = {
            "present_for_seconds": round(present_for, 1),
            "required_seconds": required_seconds,
            "next_alert_in_seconds": round(next_alert_in, 1),
        }
        self._log_detection("minimap_red", result, log_extra)

        if (first_alert_pending and ready_for_first_alert) or ready_for_repeat_alert:
            result.info["present_for_seconds"] = round(present_for, 1)
            self._fire_alert("minimap_red", result)
            return True
        return False

    def status_snapshot(self) -> dict[str, Any]:
        active_alert: str | None = None
        if self.active.get("captcha", False):
            active_alert = "lie_detector"
        elif self.active.get("minimap_red", False) and self.last_alert.get("minimap_red", 0.0) > 0.0:
            active_alert = "player_detected"

        return {
            "lie_last_seen_epoch": self.last_seen_epoch.get("captcha"),
            "player_last_seen_epoch": self.last_seen_epoch.get("minimap_red"),
            "lie_active": bool(self.active.get("captcha", False)),
            "player_present": bool(self.active.get("minimap_red", False)),
            "player_alerting": bool(
                self.active.get("minimap_red", False)
                and self.last_alert.get("minimap_red", 0.0) > 0.0
            ),
            "active_alert": active_alert,
        }

    def _log_detection(
        self,
        kind: str,
        result: DetectionResult,
        extra_info: dict[str, Any] | None = None,
    ) -> None:
        now = time.monotonic()
        log_interval = float(self.config["alerts"]["detection_log_interval_seconds"])
        if now - self.last_detection_log.get(kind, 0.0) < log_interval:
            return

        info = dict(result.info)
        if extra_info:
            info.update(extra_info)
        self.logger.info(
            "%s detected confidence=%.3f info=%s",
            kind,
            result.confidence,
            json.dumps(info, sort_keys=True),
        )
        self.last_detection_log[kind] = now

    def _print_state_change(
        self,
        kind: str,
        state: str,
        extra_info: dict[str, Any] | None = None,
    ) -> None:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if kind == "captcha":
            label = "CAPTCHA/lie detector"
        elif kind == "minimap_red":
            label = "red minimap marker"
        else:
            label = kind
        suffix = ""
        if extra_info:
            suffix = " " + json.dumps(extra_info, sort_keys=True)
        print(f"[{stamp}] Maple detection: {label} {state}.{suffix}", flush=True)

    def _fire_alert(self, kind: str, result: DetectionResult) -> None:
        message = self._message_for(kind, result)
        print(message, flush=True)
        self.logger.info("Alert fired: %s", message)
        self._play_sound(kind)
        send_remote_notifications(self.config, self.logger, message)
        self.last_alert[kind] = time.monotonic()

    def _message_for(self, kind: str, result: DetectionResult) -> str:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if kind == "captcha":
            return f"[{stamp}] Maple alert: CAPTCHA/lie detector candidate. confidence={result.confidence:.3f}"
        if kind == "minimap_red":
            pixels = result.info.get("red_pixels", "?")
            percent = result.info.get("red_percent", "?")
            present_for = result.info.get("present_for_seconds", "?")
            return f"[{stamp}] Maple alert: red minimap marker. confidence={result.confidence:.3f} red_pixels={pixels} red_percent={percent} present_for={present_for}s"
        return f"[{stamp}] Maple alert: {kind}. confidence={result.confidence:.3f}"

    def _play_sound(self, kind: str) -> None:
        if not self.config["alerts"]["audible"]:
            return
        try:
            play_alert_sound_pattern(kind, read_alert_volume_percent(self.config, kind=kind))
        except Exception as exc:
            self.logger.warning("Could not play alert sound: %s", exc)

def draw_captcha_debug(bgr: np.ndarray, result: DetectionResult) -> np.ndarray:
    out = bgr.copy()
    cv2.putText(
        out,
        f"captcha conf={result.confidence:.3f}",
        (8, 22),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0, 255, 255) if result.detected else (255, 255, 255),
        2,
        cv2.LINE_AA,
    )

    box = result.info.get("heuristic", {}).get("box") or result.info.get("template", {}).get("box")
    if box:
        x, y, w, h = [int(v) for v in box]
        cv2.rectangle(out, (x, y), (x + w, y + h), (0, 255, 255), 2)
    return out


def draw_minimap_debug(bgr: np.ndarray, result: DetectionResult) -> np.ndarray:
    out = bgr.copy()
    label = (
        f"red px={result.info['red_pixels']} "
        f"pct={result.info['red_percent']:.5f} "
        f"blob={result.info['largest_blob_area']}"
    )
    cv2.putText(
        out,
        label,
        (8, 22),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (0, 255, 255) if result.detected else (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    return out


def show_debug_windows(
    captcha_bgr: np.ndarray,
    minimap_bgr: np.ndarray,
    minimap_mask: np.ndarray,
    captcha_result: DetectionResult,
    minimap_result: DetectionResult,
) -> bool:
    cv2.imshow("CAPTCHA ROI", draw_captcha_debug(captcha_bgr, captcha_result))
    cv2.imshow("Minimap ROI", draw_minimap_debug(minimap_bgr, minimap_result))
    cv2.imshow("Minimap Red Mask", minimap_mask)
    key = cv2.waitKey(1) & 0xFF
    return key not in (ord("q"), 27)


def save_debug_crops(
    config: dict[str, Any],
    captcha_bgr: np.ndarray,
    minimap_bgr: np.ndarray,
    minimap_mask: np.ndarray,
    suffix: str,
) -> None:
    crop_dir = resolve_config_path(config, config["debug"]["crop_dir"])
    crop_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    cv2.imwrite(str(crop_dir / f"{stamp}_{suffix}_captcha_roi.png"), captcha_bgr)
    cv2.imwrite(str(crop_dir / f"{stamp}_{suffix}_minimap_roi.png"), minimap_bgr)
    cv2.imwrite(str(crop_dir / f"{stamp}_{suffix}_minimap_mask.png"), minimap_mask)


def crop_square_around_box(bgr: np.ndarray, box: list[int], size: int) -> np.ndarray:
    height, width = bgr.shape[:2]
    size = max(1, min(int(size), width, height))
    x, y, w, h = [int(v) for v in box]
    center_x = x + w / 2.0
    center_y = y + h / 2.0

    left = int(round(center_x - size / 2.0))
    top = int(round(center_y - size / 2.0))
    left = max(0, min(width - size, left))
    top = max(0, min(height - size, top))
    return bgr[top : top + size, left : left + size].copy()


class RollingBoxCropSaver:
    def __init__(
        self,
        config: dict[str, Any],
        logger: logging.Logger,
        enabled_key: str,
        dir_key: str,
        size_key: str,
        limit_key: str,
        filename_prefix: str,
    ) -> None:
        self.config = config
        self.logger = logger
        self.enabled_key = enabled_key
        self.dir_key = dir_key
        self.size_key = size_key
        self.limit_key = limit_key
        self.filename_prefix = filename_prefix
        self.index: int | None = None

    def save(self, bgr: np.ndarray, box: list[int] | None, status: str) -> Path | None:
        debug_cfg = self.config["debug"]
        if not debug_cfg.get(self.enabled_key, True):
            return None

        if not box:
            return None

        limit = max(1, int(debug_cfg.get(self.limit_key, 10)))
        size = max(1, int(debug_cfg.get(self.size_key, 100)))
        crop_dir = resolve_config_path(self.config, debug_cfg[self.dir_key])
        crop_dir.mkdir(parents=True, exist_ok=True)

        crop = crop_square_around_box(bgr, box, size)
        index_path = crop_dir / "_next_slot.txt"
        if self.index is None:
            try:
                self.index = int(index_path.read_text(encoding="utf-8").strip())
            except Exception:
                self.index = 0
        slot = self.index % limit
        self.index = (slot + 1) % limit
        index_path.write_text(str(self.index), encoding="utf-8")

        path = crop_dir / f"{self.filename_prefix}_{slot:02d}_{status}.png"
        # Remove the previous status variant for the same slot so there are never more than N PNGs.
        for old_path in crop_dir.glob(f"{self.filename_prefix}_{slot:02d}_*.png"):
            if old_path != path:
                old_path.unlink(missing_ok=True)

        cv2.imwrite(str(path), crop)
        crop_files = sorted(
            crop_dir.glob(f"{self.filename_prefix}_*.png"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for old_path in crop_files[limit:]:
            old_path.unlink(missing_ok=True)
        return path


def make_blue_block_crop_saver(config: dict[str, Any], logger: logging.Logger) -> RollingBoxCropSaver:
    return RollingBoxCropSaver(
        config,
        logger,
        "save_blue_block_crops",
        "blue_block_crop_dir",
        "blue_block_crop_size",
        "blue_block_crop_limit",
        "blue_block",
    )


def make_red_dot_crop_saver(config: dict[str, Any], logger: logging.Logger) -> RollingBoxCropSaver:
    return RollingBoxCropSaver(
        config,
        logger,
        "save_red_dot_crops",
        "red_dot_crop_dir",
        "red_dot_crop_size",
        "red_dot_crop_limit",
        "red_dot",
    )


def log_monitor_status(
    logger: logging.Logger,
    base_source: str,
    base_rect: Rect,
    captcha_result: DetectionResult,
    minimap_result: DetectionResult,
    minimap_seen_since: float | None,
    runtime_scale_info: dict[str, Any] | None = None,
) -> None:
    now = time.monotonic()
    if minimap_seen_since is None:
        red_present_for = 0.0
    else:
        red_present_for = now - minimap_seen_since

    logger.info(
        (
            "Monitoring source=%s rect=%sx%s+%s+%s "
            "pixel_scale=%s "
            "captcha_conf=%.3f captcha_detected=%s "
            "red_detected=%s red_pixels=%s red_present_for=%.1fs"
        ),
        base_source,
        base_rect.width,
        base_rect.height,
        base_rect.left,
        base_rect.top,
        runtime_scale_info.get("pixel_scale", "?") if runtime_scale_info else "?",
        captcha_result.confidence,
        captcha_result.detected,
        minimap_result.detected,
        minimap_result.info.get("red_pixels", "?"),
        red_present_for,
    )


def print_window_list() -> None:
    windows = list_windows()
    if not windows:
        print("No windows found by pygetwindow/win32gui.")
        return
    for title, rect in windows:
        safe_title = title.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
            sys.stdout.encoding or "utf-8", errors="replace"
        )
        print(f"{safe_title} | left={rect.left} top={rect.top} width={rect.width} height={rect.height}")


def is_sensitive_config_key(key: str) -> bool:
    folded = key.casefold()
    return any(fragment in folded for fragment in SENSITIVE_KEY_FRAGMENTS)


def redact_config_value(key: str, value: Any) -> Any:
    if is_sensitive_config_key(key):
        if value is None or value == "":
            return ""
        return REDACTED_VALUE
    if isinstance(value, dict):
        return {str(child_key): redact_config_value(str(child_key), child_value) for child_key, child_value in value.items()}
    if isinstance(value, list):
        return [redact_config_value(key, item) for item in value]
    return value


def build_redacted_config(config: dict[str, Any]) -> dict[str, Any]:
    redacted = {str(key): redact_config_value(str(key), value) for key, value in config.items()}
    notification_settings = read_notification_settings(config)
    if notification_settings:
        redacted["runtime_notification_settings"] = redact_config_value("runtime_notification_settings", notification_settings)
    return redacted


def read_release_manifest(base_dir: Path) -> dict[str, Any]:
    path = base_dir / RELEASE_MANIFEST_NAME
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def build_info_payload(base_dir: Path) -> dict[str, Any]:
    manifest = read_release_manifest(base_dir)
    return {
        "app_name": APP_NAME,
        "app_version": APP_VERSION,
        "release_manifest": manifest,
    }


def run_build_info(base_dir: Path) -> int:
    print(json.dumps(build_info_payload(base_dir), indent=2, sort_keys=True), flush=True)
    return 0


def config_issue(severity: str, code: str, path: str, message: str) -> dict[str, str]:
    return {
        "severity": severity,
        "code": code,
        "path": path,
        "message": message,
    }


def validate_numeric_range(
    issues: list[dict[str, str]],
    value: Any,
    *,
    path: str,
    code: str,
    min_value: float,
    max_value: float,
) -> None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        issues.append(config_issue("error", code, path, f"{path} must be a number."))
        return
    if number < min_value or number > max_value:
        issues.append(
            config_issue(
                "error",
                code,
                path,
                f"{path} must be between {min_value:g} and {max_value:g}.",
            )
        )


def validate_roi_config(issues: list[dict[str, str]], config: dict[str, Any], name: str) -> None:
    roi_cfg = config.get("roi", {}).get(name, {})
    values: dict[str, float] = {}
    for key in ("x1", "y1", "x2", "y2"):
        path = f"roi.{name}.{key}"
        try:
            values[key] = float(roi_cfg[key])
        except (KeyError, TypeError, ValueError):
            issues.append(config_issue("error", f"{name}_roi_invalid", path, f"{path} must be a number from 0 to 1."))
            return
        if values[key] < 0.0 or values[key] > 1.0:
            issues.append(config_issue("error", f"{name}_roi_invalid", path, f"{path} must be between 0 and 1."))
    if values["x2"] <= values["x1"] or values["y2"] <= values["y1"]:
        issues.append(
            config_issue(
                "error",
                f"{name}_roi_order",
                f"roi.{name}",
                f"roi.{name} must have x2>x1 and y2>y1.",
            )
        )


def validate_config(config: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    capture_cfg = config.get("capture", {})
    alerts_cfg = config.get("alerts", {})

    if bool(capture_cfg.get("target_window", False)) and not str(capture_cfg.get("window_title", "")).strip():
        issues.append(
            config_issue(
                "error",
                "window_title_empty",
                "capture.window_title",
                "capture.window_title is required when target_window is true.",
            )
        )

    try:
        fps = float(capture_cfg.get("fps", DEFAULT_CONFIG["capture"]["fps"]))
        if fps <= 0:
            issues.append(config_issue("error", "capture_fps_invalid", "capture.fps", "capture.fps must be above 0."))
        elif fps < 0.05:
            issues.append(
                config_issue(
                    "warning",
                    "capture_fps_clamped_low",
                    "capture.fps",
                    "capture.fps is below 0.05 and will be clamped.",
                )
            )
        elif fps > 2.0:
            issues.append(
                config_issue(
                    "warning",
                    "capture_fps_high",
                    "capture.fps",
                    "capture.fps is high for a low-CPU monitor.",
                )
            )
    except (TypeError, ValueError):
        issues.append(config_issue("error", "capture_fps_invalid", "capture.fps", "capture.fps must be numeric."))

    validate_roi_config(issues, config, "captcha")
    validate_roi_config(issues, config, "minimap")

    for key in ("alert_volume_percent", "lie_detect_volume_percent", "player_detected_volume_percent"):
        if key in alerts_cfg:
            validate_numeric_range(
                issues,
                alerts_cfg.get(key),
                path=f"alerts.{key}",
                code=f"{key}_range",
                min_value=0,
                max_value=250,
            )

    notifications = notification_readiness_summary(config)
    telegram_token = bool(notification_value(config, "telegram", "bot_token"))
    telegram_chat = bool(notification_value(config, "telegram", "chat_id"))
    discord_token = bool(notification_value(config, "discord", "bot_token"))
    discord_user = bool(notification_value(config, "discord", "user_id"))
    discord_webhook = bool(notification_value(config, "discord", "webhook_url"))

    if telegram_token != telegram_chat:
        issues.append(
            config_issue(
                "warning",
                "telegram_incomplete",
                "telegram",
                "Telegram needs both bot_token and chat_id to send alerts.",
            )
        )
    if (discord_token != discord_user) and not discord_webhook:
        issues.append(
            config_issue(
                "warning",
                "discord_dm_incomplete",
                "discord",
                "Discord DM needs both bot_token and user_id, or a webhook_url.",
            )
        )
    if bool(notifications["remote_enabled"]) and not (
        bool(notifications["telegram_configured"]) or bool(notifications["discord_configured"])
    ):
        issues.append(
            config_issue(
                "warning",
                "remote_alerts_no_service",
                "notifications.remote_enabled",
                "Remote alerts are enabled but no complete Telegram or Discord destination is configured.",
            )
        )
    if not bool(alerts_cfg.get("safe_mode", True)) and not bool(notifications["remote_enabled"]):
        issues.append(
            config_issue(
                "warning",
                "legacy_remote_mode",
                "alerts.safe_mode",
                "safe_mode is false; prefer notifications.remote_enabled plus runtime DM settings for private credentials.",
            )
        )

    return issues


def count_label(count: int, word: str) -> str:
    suffix = "" if count == 1 else "s"
    return f"{count} {word}{suffix}"


def collect_sensitive_values(config: dict[str, Any]) -> set[str]:
    values: set[str] = set()

    def walk(key: str, value: Any) -> None:
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                walk(str(child_key), child_value)
            return
        if isinstance(value, list):
            for item in value:
                walk(key, item)
            return
        if is_sensitive_config_key(key) and isinstance(value, str) and value.strip():
            values.add(value.strip())

    walk("config", config)
    walk("notification_settings", read_notification_settings(config))
    return values


def redact_sensitive_text(text: str, config: dict[str, Any]) -> str:
    redacted = text
    redacted = re.sub(
        r"https://api\.telegram\.org/bot[^/\s]+/sendMessage",
        "https://api.telegram.org/bot<redacted>/sendMessage",
        redacted,
    )
    redacted = re.sub(
        r"https://(?:canary\.|ptb\.)?discord(?:app)?\.com/api/webhooks/\S+",
        "<discord-webhook-redacted>",
        redacted,
    )
    for value in sorted(collect_sensitive_values(config), key=len, reverse=True):
        if len(value) >= 3:
            redacted = redacted.replace(value, REDACTED_VALUE)
    return redacted


def matching_window_candidates(
    config: dict[str, Any],
    windows: list[tuple[str, Rect]] | None = None,
) -> list[tuple[str, Rect]]:
    capture_cfg = config["capture"]
    needle = str(capture_cfg.get("window_title", "")).casefold().strip()
    if not needle:
        return []
    ignored = ignored_window_title_substrings(capture_cfg)
    available_windows = list_windows() if windows is None else windows
    return [
        (title, rect)
        for title, rect in available_windows
        if needle in title.casefold() and not is_ignored_window_title(title, ignored)
    ]


def notification_readiness_summary(config: dict[str, Any]) -> dict[str, Any]:
    telegram_configured = bool(notification_value(config, "telegram", "bot_token")) and bool(
        notification_value(config, "telegram", "chat_id")
    )
    discord_dm_configured = bool(notification_value(config, "discord", "bot_token")) and bool(
        notification_value(config, "discord", "user_id")
    )
    discord_webhook_configured = bool(notification_value(config, "discord", "webhook_url"))
    return {
        "remote_enabled": remote_notifications_enabled(config),
        "telegram_configured": telegram_configured,
        "telegram_enabled": notification_service_enabled(config, "telegram"),
        "discord_configured": discord_dm_configured or discord_webhook_configured,
        "discord_dm_configured": discord_dm_configured,
        "discord_webhook_configured": discord_webhook_configured,
        "discord_enabled": notification_service_enabled(config, "discord"),
    }


def format_yes_no(value: bool) -> str:
    return "yes" if value else "no"


def format_system_volume_state(state: SystemVolumeState) -> str:
    if state.percent is None and state.muted is None:
        detail = f"unknown ({state.error})" if state.error else "unknown"
        return f"System Volume: {detail}; warning threshold={SYSTEM_VOLUME_WARNING_PERCENT}%"
    muted = "yes" if state.muted else "no"
    percent = "unknown" if state.percent is None else f"{state.percent}%"
    attention = "yes" if state.needs_attention else "no"
    return f"System Volume: {percent}; muted={muted}; below threshold={attention}; warning threshold={SYSTEM_VOLUME_WARNING_PERCENT}%"


def required_portable_files(config_dir: Path) -> list[tuple[str, Path]]:
    return [
        ("Launcher", config_dir / "START_MAPLE_ALERT.bat"),
        ("App", config_dir / "MapleAlert.exe"),
        ("Config", config_dir / "config.toml"),
        ("Watchdog", config_dir / "_internal" / "watchdog_supervisor.ps1"),
        ("Lie alert sound", config_dir / "alert_sounds" / "captcha_100pct.wav"),
        ("Player alert sound", config_dir / "alert_sounds" / "minimap_red_100pct.wav"),
    ]


def build_setup_check_report(
    config: dict[str, Any],
    config_path: Path,
    *,
    windows: list[tuple[str, Rect]] | None = None,
    system_volume_state: SystemVolumeState | None = None,
) -> str:
    config_dir = Path(config["_config_dir"])
    capture_cfg = config["capture"]
    lines = [
        "Maple Alert setup check",
        f"Config: {config_path.resolve()}",
        f"Folder: {config_dir.resolve()}",
    ]

    for label, path in required_portable_files(config_dir):
        status = "OK" if path.exists() else "MISSING"
        lines.append(f"{label}: {status} ({path.name})")

    loaded_files = config.get("_loaded_config_files", [])
    if loaded_files:
        lines.append(f"Loaded Config Files: {len(loaded_files)}")

    issues = validate_config(config)
    errors = sum(1 for issue in issues if issue.get("severity") == "error")
    warnings = sum(1 for issue in issues if issue.get("severity") == "warning")
    lines.append(f"Config Validation: {count_label(errors, 'error')}, {count_label(warnings, 'warning')}")
    for issue in issues[:5]:
        lines.append(
            (
                f"  - {issue.get('severity', 'warning').upper()} "
                f"{issue.get('path', 'config')}: {issue.get('message', '')}"
            )
        )

    if bool(capture_cfg.get("target_window", False)):
        candidates = matching_window_candidates(config, windows)
        if candidates:
            title, rect = candidates[0]
            scale_info = compute_scale_info(config, rect)
            lines.append(
                (
                    f"Maple Window: FOUND \"{title}\" "
                    f"left={rect.left} top={rect.top} resolution={rect.width}x{rect.height} "
                    f"pixel_scale={scale_info.pixel_scale:.4f} "
                    f"scale_x={scale_info.scale_x:.4f} scale_y={scale_info.scale_y:.4f}"
                )
            )
            base = Rect(0, 0, rect.width, rect.height)
            captcha_roi = roi_to_rect(base, config["roi"]["captcha"])
            minimap_roi = roi_to_rect(base, config["roi"]["minimap"])
            lines.append(f"Lie ROI: {captcha_roi.width}x{captcha_roi.height}+{captcha_roi.left}+{captcha_roi.top}")
            lines.append(f"Minimap ROI: {minimap_roi.width}x{minimap_roi.height}+{minimap_roi.left}+{minimap_roi.top}")
        else:
            lines.append(
                (
                    "Maple Window: NOT FOUND; monitor fallback will be used until a non-alert "
                    f"window containing \"{capture_cfg.get('window_title', '')}\" is visible."
                )
            )
    else:
        lines.append(f"Capture: monitor_index={capture_cfg.get('monitor_index', 1)} (target_window=false)")

    volume_state = system_volume_state if system_volume_state is not None else read_system_volume_state()
    lines.append(format_system_volume_state(volume_state))
    lines.append(f"Lie Detect Volume: {read_alert_volume_percent(config, kind='captcha')}%")
    lines.append(f"Player Detect Volume: {read_alert_volume_percent(config, kind='minimap_red')}%")

    notifications = notification_readiness_summary(config)
    lines.append(
        (
            "Remote Alerts: "
            f"enabled={format_yes_no(bool(notifications['remote_enabled']))}; "
            f"Telegram configured={format_yes_no(bool(notifications['telegram_configured']))} "
            f"active={format_yes_no(bool(notifications['telegram_enabled']))}; "
            f"Discord configured={format_yes_no(bool(notifications['discord_configured']))} "
            f"active={format_yes_no(bool(notifications['discord_enabled']))}"
        )
    )
    lines.append("Mode: visual detection and local/remote alerts.")
    return "\n".join(lines)


def tail_text_file(path: Path, max_lines: int = 200) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return ""
    return "\n".join(lines[-max_lines:])


def unique_diagnostic_bundle_dir(output_root: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = output_root / f"maple_alert_diagnostics_{stamp}"
    candidate = base
    suffix = 1
    while candidate.exists():
        suffix += 1
        candidate = output_root / f"{base.name}_{suffix}"
    return candidate


def write_diagnostic_bundle(
    config: dict[str, Any],
    config_path: Path,
    *,
    output_root: Path | None = None,
    windows: list[tuple[str, Rect]] | None = None,
    system_volume_state: SystemVolumeState | None = None,
) -> Path:
    root = output_root if output_root is not None else resolve_config_path(config, "runtime/diagnostics")
    bundle_dir = unique_diagnostic_bundle_dir(root)
    runtime_dir = bundle_dir / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=False)

    (bundle_dir / "README.txt").write_text(
        (
            "Maple Alert diagnostics bundle\n"
            "This bundle is text/JSON only. It does not include screenshots or debug crop images.\n"
            "Remote alert tokens, IDs, and webhook URLs are redacted.\n"
        ),
        encoding="utf-8",
    )
    (bundle_dir / "summary.txt").write_text(
        build_setup_check_report(
            config,
            config_path,
            windows=windows,
            system_volume_state=system_volume_state,
        ),
        encoding="utf-8",
    )
    (bundle_dir / "config_redacted.json").write_text(
        json.dumps(build_redacted_config(config), indent=2, sort_keys=True),
        encoding="utf-8",
    )

    watchdog_cfg = config.get("watchdog", {})
    runtime_files = {
        "heartbeat.json": watchdog_cfg.get("heartbeat_file", "runtime/heartbeat.json"),
        "watchdog_heartbeat.json": watchdog_cfg.get("watchdog_heartbeat_file", "runtime/watchdog_heartbeat.json"),
        "supervisor_heartbeat.json": watchdog_cfg.get("supervisor_heartbeat_file", "runtime/supervisor_heartbeat.json"),
    }
    for output_name, configured_path in runtime_files.items():
        payload = read_json_file(resolve_config_path(config, str(configured_path)))
        (runtime_dir / output_name).write_text(
            json.dumps(redact_config_value(output_name, payload), indent=2, sort_keys=True),
            encoding="utf-8",
        )

    log_path = resolve_config_path(config, config["debug"]["log_file"])
    log_tail = tail_text_file(log_path)
    (bundle_dir / "detections_tail.txt").write_text(
        redact_sensitive_text(log_tail or "(no detection log found)", config),
        encoding="utf-8",
    )
    return bundle_dir


def run_setup_check(config: dict[str, Any], config_path: Path) -> int:
    print(build_setup_check_report(config, config_path), flush=True)
    return 0


def run_diagnostics(config: dict[str, Any], config_path: Path, output_dir: str) -> int:
    output_root = Path(output_dir).expanduser()
    if not output_root.is_absolute():
        output_root = Path(config["_config_dir"]) / output_root
    bundle_dir = write_diagnostic_bundle(config, config_path, output_root=output_root)
    print(f"Diagnostics bundle written: {bundle_dir}", flush=True)
    return 0


def run_validate_config(config: dict[str, Any]) -> int:
    issues = validate_config(config)
    errors = sum(1 for issue in issues if issue.get("severity") == "error")
    warnings = sum(1 for issue in issues if issue.get("severity") == "warning")
    print(f"Config Validation: {count_label(errors, 'error')}, {count_label(warnings, 'warning')}", flush=True)
    for issue in issues:
        print(
            (
                f"{issue.get('severity', 'warning').upper()} "
                f"{issue.get('path', 'config')}: {issue.get('message', '')}"
            ),
            flush=True,
        )
    return 1 if errors else 0


def process_is_alive(pid: int | None) -> bool:
    if not pid or pid <= 0 or pid == os.getpid():
        return True

    if os.name == "nt":
        try:
            import ctypes

            synchronize = 0x00100000
            wait_timeout = 0x00000102
            handle = ctypes.windll.kernel32.OpenProcess(synchronize, False, int(pid))
            if not handle:
                return False
            try:
                return ctypes.windll.kernel32.WaitForSingleObject(handle, 0) == wait_timeout
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        except Exception:
            return False

    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def configured_parent_pid(config: dict[str, Any]) -> int | None:
    try:
        parent_pid = int(config.get("_parent_pid") or 0)
    except (TypeError, ValueError):
        return None
    return parent_pid if parent_pid > 0 else None


class GUID(ctypes.Structure if os.name == "nt" else object):
    if os.name == "nt":
        _fields_ = [
            ("Data1", ctypes.c_ulong),
            ("Data2", ctypes.c_ushort),
            ("Data3", ctypes.c_ushort),
            ("Data4", ctypes.c_ubyte * 8),
        ]


def guid_from_string(value: str) -> Any:
    parsed = uuid.UUID(value)
    data4 = (ctypes.c_ubyte * 8).from_buffer_copy(parsed.bytes[8:])
    return GUID(parsed.time_low, parsed.time_mid, parsed.time_hi_version, data4)


def release_com_object(ptr: Any) -> None:
    if not ptr:
        return
    try:
        vtbl = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl[2])
        release(ptr)
    except Exception:
        pass


def read_system_volume_state() -> SystemVolumeState:
    if os.name != "nt":
        return SystemVolumeState(None, None, "system volume check only supports Windows")

    try:
        import ctypes
        from ctypes import wintypes
    except Exception as exc:
        return SystemVolumeState(None, None, str(exc))

    ole32 = ctypes.OleDLL("ole32")
    co_initialized = False
    if ole32.CoInitialize(None) >= 0:
        co_initialized = True

    enumerator = ctypes.c_void_p()
    device = ctypes.c_void_p()
    endpoint = ctypes.c_void_p()
    try:
        clsid_mmdevice_enumerator = guid_from_string("BCDE0395-E52F-467C-8E3D-C4579291692E")
        iid_immdevice_enumerator = guid_from_string("A95664D2-9614-4F35-A746-DE8DB63617E6")
        iid_iaudio_endpoint_volume = guid_from_string("5CDF2C82-841E-4546-9722-0CF74078229A")
        clsctx_all = 23
        e_render = 0
        e_console = 0

        hr = ole32.CoCreateInstance(
            ctypes.byref(clsid_mmdevice_enumerator),
            None,
            clsctx_all,
            ctypes.byref(iid_immdevice_enumerator),
            ctypes.byref(enumerator),
        )
        if hr != 0 or not enumerator:
            return SystemVolumeState(None, None, f"CoCreateInstance failed hr=0x{hr & 0xFFFFFFFF:08x}")

        enum_vtbl = ctypes.cast(enumerator, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        get_default_audio_endpoint = ctypes.WINFUNCTYPE(
            ctypes.c_long,
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_void_p),
        )(enum_vtbl[4])
        hr = get_default_audio_endpoint(enumerator, e_render, e_console, ctypes.byref(device))
        if hr != 0 or not device:
            return SystemVolumeState(None, None, f"GetDefaultAudioEndpoint failed hr=0x{hr & 0xFFFFFFFF:08x}")

        device_vtbl = ctypes.cast(device, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        activate = ctypes.WINFUNCTYPE(
            ctypes.c_long,
            ctypes.c_void_p,
            ctypes.POINTER(GUID),
            wintypes.DWORD,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        )(device_vtbl[3])
        hr = activate(
            device,
            ctypes.byref(iid_iaudio_endpoint_volume),
            clsctx_all,
            None,
            ctypes.byref(endpoint),
        )
        if hr != 0 or not endpoint:
            return SystemVolumeState(None, None, f"Activate IAudioEndpointVolume failed hr=0x{hr & 0xFFFFFFFF:08x}")

        endpoint_vtbl = ctypes.cast(endpoint, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        get_master_volume = ctypes.WINFUNCTYPE(
            ctypes.c_long,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_float),
        )(endpoint_vtbl[9])
        get_mute = ctypes.WINFUNCTYPE(
            ctypes.c_long,
            ctypes.c_void_p,
            ctypes.POINTER(wintypes.BOOL),
        )(endpoint_vtbl[15])

        scalar = ctypes.c_float()
        muted = wintypes.BOOL()
        hr = get_master_volume(endpoint, ctypes.byref(scalar))
        if hr != 0:
            return SystemVolumeState(None, None, f"GetMasterVolumeLevelScalar failed hr=0x{hr & 0xFFFFFFFF:08x}")
        hr = get_mute(endpoint, ctypes.byref(muted))
        if hr != 0:
            return SystemVolumeState(None, None, f"GetMute failed hr=0x{hr & 0xFFFFFFFF:08x}")

        percent = max(0, min(100, int(round(float(scalar.value) * 100))))
        return SystemVolumeState(percent, bool(muted.value), None)
    except Exception as exc:
        return SystemVolumeState(None, None, str(exc))
    finally:
        release_com_object(endpoint)
        release_com_object(device)
        release_com_object(enumerator)
        if co_initialized:
            try:
                ole32.CoUninitialize()
            except Exception:
                pass


def play_alert_sound_pattern(kind: str, volume_percent: int) -> None:
    wav_bytes = synthesize_alert_wav_bytes(kind, volume_percent)
    if not wav_bytes:
        return
    import winsound

    winsound.PlaySound(wav_bytes, winsound.SND_MEMORY | winsound.SND_SYNC)


def alert_segments_for_kind(kind: str) -> list[tuple[int, int]]:
    if kind == "captcha":
        return [(1300, 450), (1600, 450)]
    if kind == "watchdog":
        return [(1800, 250), (900, 250)] * 3
    return [(900, 250), (900, 250)]


def volume_to_pcm_amplitude(volume_percent: int | float) -> int:
    value = max(0, min(250, int(round(float(volume_percent)))))
    # 100% is intentionally below digital full-scale so 250% has headroom.
    return int(round(30000 * (value / 250.0)))


def synthesize_alert_wav_bytes(kind: str, volume_percent: int | float, sample_rate: int = 44100) -> bytes:
    amplitude = volume_to_pcm_amplitude(volume_percent)
    if amplitude <= 0:
        return b""

    segments: list[np.ndarray] = []
    for frequency, duration_ms in alert_segments_for_kind(kind):
        sample_count = max(1, int(round(sample_rate * duration_ms / 1000.0)))
        t = np.arange(sample_count, dtype=np.float64) / float(sample_rate)
        tone = np.sin(2.0 * math.pi * float(frequency) * t)

        fade_count = min(int(sample_rate * 0.004), sample_count // 2)
        if fade_count > 1:
            ramp = np.linspace(0.0, 1.0, fade_count, dtype=np.float64)
            tone[:fade_count] *= ramp
            tone[-fade_count:] *= ramp[::-1]

        peak = float(np.max(np.abs(tone)))
        if peak > 0:
            tone *= amplitude / peak
        segments.append(np.rint(tone).astype(np.int16))

    samples = np.concatenate(segments) if segments else np.array([], dtype=np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(samples.tobytes())
    return buffer.getvalue()


def export_alert_wavs(config: dict[str, Any], output_dir: str) -> int:
    output_path = Path(output_dir).expanduser()
    if not output_path.is_absolute():
        output_path = Path(config["_config_dir"]) / output_path
    output_path.mkdir(parents=True, exist_ok=True)

    volumes = sorted(
        {
            25,
            100,
            200,
            250,
            read_alert_volume_percent(config, kind="captcha"),
            read_alert_volume_percent(config, kind="minimap_red"),
        }
    )
    for kind in ("captcha", "minimap_red", "watchdog"):
        for volume in volumes:
            wav_path = output_path / f"{kind}_{volume}pct.wav"
            wav_path.write_bytes(synthesize_alert_wav_bytes(kind, volume))
            print(wav_path)
    return 0


def write_heartbeat(
    config: dict[str, Any],
    source: str,
    rect: Rect,
    alert_status: dict[str, Any] | None = None,
) -> None:
    path = resolve_config_path(config, config["watchdog"]["heartbeat_file"])
    path.parent.mkdir(parents=True, exist_ok=True)
    target_window = bool(config["capture"].get("target_window", False))
    payload = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "epoch_seconds": time.time(),
        "pid": os.getpid(),
        "source": source,
        "rect": rect.__dict__,
        "resolution": [rect.width, rect.height],
        "target_window": target_window,
        "window_title": str(config["capture"].get("window_title", "")),
        "maple_detected": (source == "window") if target_window else True,
        "runtime_scale": config.get("_runtime_scale", {}),
        "alert_status": alert_status or {
            "lie_last_seen_epoch": None,
            "player_last_seen_epoch": None,
            "lie_active": False,
            "player_present": False,
            "player_alerting": False,
            "active_alert": None,
        },
    }
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    temp_path.replace(path)


def write_watchdog_heartbeat(
    config: dict[str, Any],
    child_pid: int | None,
    restart_count: int,
    status: str,
    monitor_health: dict[str, Any] | None = None,
) -> None:
    path = resolve_config_path(
        config,
        config["watchdog"].get("watchdog_heartbeat_file", "runtime/watchdog_heartbeat.json"),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "epoch_seconds": time.time(),
        "pid": os.getpid(),
        "child_pid": child_pid,
        "restart_count": restart_count,
        "status": status,
    }
    if monitor_health is not None:
        payload["monitor_health"] = monitor_health
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    temp_path.replace(path)


def play_watchdog_sound() -> None:
    try:
        play_alert_sound_pattern("watchdog", 200)
    except Exception:
        pass


def watchdog_alert(config: dict[str, Any], logger: logging.Logger, message: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full_message = f"[{stamp}] Maple Alert watchdog: {message}"
    print(full_message, flush=True)
    logger.error(full_message)
    play_watchdog_sound()
    send_remote_notifications(config, logger, full_message)


def watchdog_notice(logger: logging.Logger, message: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full_message = f"[{stamp}] Maple Alert watchdog: {message}"
    print(full_message, flush=True)
    logger.warning(full_message)


def monitor_heartbeat_available(path: Path, stale_seconds: float) -> bool:
    age = heartbeat_age(path)
    return age is not None and age <= stale_seconds


def maybe_watchdog_health_alarm(
    config: dict[str, Any],
    logger: logging.Logger,
    tracker: WatchdogFailureTracker,
    snapshot: dict[str, Any],
    message: str,
) -> bool:
    now = time.time()
    if not tracker.should_sound(snapshot, now):
        return False
    title = watchdog_health_title(snapshot)
    if title:
        message = f"{message}; {title}"
    watchdog_alert(config, logger, message)
    tracker.mark_sounded(now)
    return True


def child_monitor_command(config_path: Path, parent_pid: int | None = None) -> list[str]:
    if getattr(sys, "frozen", False):
        command = [str(Path(sys.executable).resolve()), "--config", str(config_path)]
    else:
        command = [sys.executable, str(Path(__file__).resolve()), "--config", str(config_path)]
    if parent_pid:
        command.extend(["--parent-pid", str(parent_pid)])
    return command


def stop_child(process: subprocess.Popen[Any], logger: logging.Logger) -> None:
    if process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=5)
    except Exception:
        logger.warning("Child did not terminate cleanly; killing it")
        try:
            process.kill()
        except Exception:
            pass


def run_watchdog(config: dict[str, Any], config_path: Path) -> int:
    logger = setup_logging(config)
    started_at_epoch = time.time()
    watchdog_cfg = config["watchdog"]
    heartbeat_path = resolve_config_path(config, watchdog_cfg["heartbeat_file"])
    watchdog_heartbeat_path = resolve_config_path(
        config,
        watchdog_cfg.get("watchdog_heartbeat_file", "runtime/watchdog_heartbeat.json"),
    )
    heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
    watchdog_heartbeat_path.parent.mkdir(parents=True, exist_ok=True)

    check_interval = max(0.5, float(watchdog_cfg["check_interval_seconds"]))
    stale_seconds = max(2.0, float(watchdog_cfg["stale_seconds"]))
    restart_delay = max(0.0, float(watchdog_cfg["restart_delay_seconds"]))
    startup_grace = max(1.0, float(watchdog_cfg["startup_grace_seconds"]))
    parent_pid = configured_parent_pid(config)
    command = child_monitor_command(config_path, os.getpid())

    logger.info(
        "Starting watchdog. monitor_heartbeat=%s watchdog_heartbeat=%s stale_seconds=%.1f",
        heartbeat_path,
        watchdog_heartbeat_path,
        stale_seconds,
    )
    print("Watchdog is running. Close this window to stop monitoring.", flush=True)

    restart_count = 0
    child: subprocess.Popen[Any] | None = None
    failure_tracker = WatchdogFailureTracker(config)
    health = failure_tracker.update(False)
    write_watchdog_heartbeat(config, None, restart_count, "starting", health)
    try:
        while True:
            if quit_requested(config, started_at_epoch):
                logger.info("Quit request received; stopping watchdog")
                print("Quit request received; stopping watchdog.", flush=True)
                return 0

            if parent_pid and not process_is_alive(parent_pid):
                logger.info("Watchdog parent pid=%s is gone; stopping watchdog", parent_pid)
                return 0

            try:
                heartbeat_path.unlink(missing_ok=True)
            except Exception:
                pass

            child = subprocess.Popen(command, cwd=str(config_path.parent))
            child_started = time.monotonic()
            logger.info("Started monitor child pid=%s", child.pid)
            health = failure_tracker.update(
                monitor_heartbeat_available(heartbeat_path, stale_seconds)
            )
            write_watchdog_heartbeat(config, child.pid, restart_count, "watching", health)

            while True:
                if quit_requested(config, started_at_epoch):
                    logger.info("Quit request received; stopping monitor child")
                    print("Quit request received; stopping monitor child.", flush=True)
                    stop_child(child, logger)
                    return 0

                if parent_pid and not process_is_alive(parent_pid):
                    logger.info("Watchdog parent pid=%s is gone; stopping monitor child", parent_pid)
                    stop_child(child, logger)
                    return 0

                time.sleep(check_interval)
                monitor_available = monitor_heartbeat_available(heartbeat_path, stale_seconds)
                health = failure_tracker.update(monitor_available)
                write_watchdog_heartbeat(config, child.pid, restart_count, "watching", health)
                maybe_watchdog_health_alarm(
                    config,
                    logger,
                    failure_tracker,
                    health,
                    "monitor health is degraded",
                )
                exit_code = child.poll()
                if exit_code is not None:
                    restart_count += 1
                    failure_tracker.record_abnormal("monitor_exited", exit_code=exit_code)
                    health = failure_tracker.update(False)
                    write_watchdog_heartbeat(config, child.pid, restart_count, "monitor_exited", health)
                    message = (
                        f"monitor exited with code {exit_code}; restarting in "
                        f"{restart_delay:.1f}s (restart #{restart_count})"
                    )
                    if not maybe_watchdog_health_alarm(
                        config,
                        logger,
                        failure_tracker,
                        health,
                        message,
                    ):
                        watchdog_notice(
                            logger,
                            (
                                f"{message}; audible alarm suppressed "
                                f"({health['crash_count_window']}/{health['crash_alert_count']} "
                                f"crashes in {minutes_label(health['window_seconds']).lower()}; "
                                f"monitor_down={health['monitor_down_seconds']}s)"
                            ),
                        )
                    break

                if heartbeat_path.exists():
                    heartbeat_age = time.time() - heartbeat_path.stat().st_mtime
                    if heartbeat_age > stale_seconds:
                        restart_count += 1
                        failure_tracker.record_abnormal("monitor_stale")
                        health = failure_tracker.update(False)
                        write_watchdog_heartbeat(config, child.pid, restart_count, "monitor_stale", health)
                        message = (
                            f"monitor heartbeat is stale ({heartbeat_age:.1f}s old); "
                            f"restarting in {restart_delay:.1f}s (restart #{restart_count})"
                        )
                        if not maybe_watchdog_health_alarm(
                            config,
                            logger,
                            failure_tracker,
                            health,
                            message,
                        ):
                            watchdog_notice(
                                logger,
                                (
                                    f"{message}; audible alarm suppressed "
                                    f"({health['crash_count_window']}/{health['crash_alert_count']} "
                                    f"failures in {minutes_label(health['window_seconds']).lower()}; "
                                    f"monitor_down={health['monitor_down_seconds']}s)"
                                ),
                            )
                        stop_child(child, logger)
                        break
                elif time.monotonic() - child_started > startup_grace:
                    restart_count += 1
                    failure_tracker.record_abnormal("monitor_missing_heartbeat")
                    health = failure_tracker.update(False)
                    write_watchdog_heartbeat(config, child.pid, restart_count, "monitor_missing_heartbeat", health)
                    message = (
                        f"monitor has not written a heartbeat after {startup_grace:.1f}s; "
                        f"restarting in {restart_delay:.1f}s (restart #{restart_count})"
                    )
                    if not maybe_watchdog_health_alarm(
                        config,
                        logger,
                        failure_tracker,
                        health,
                        message,
                    ):
                        watchdog_notice(
                            logger,
                            (
                                f"{message}; audible alarm suppressed "
                                f"({health['crash_count_window']}/{health['crash_alert_count']} "
                                f"failures in {minutes_label(health['window_seconds']).lower()}; "
                                f"monitor_down={health['monitor_down_seconds']}s)"
                            ),
                        )
                    stop_child(child, logger)
                    break

            health = failure_tracker.update(False)
            write_watchdog_heartbeat(config, None, restart_count, "restarting", health)
            time.sleep(restart_delay)
    finally:
        if child is not None:
            stop_child(child, logger)


def heartbeat_age(path: Path) -> float | None:
    try:
        if not path.exists():
            return None
        return max(0.0, time.time() - path.stat().st_mtime)
    except OSError:
        return None


def read_json_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def run_overlay(config: dict[str, Any]) -> int:
    overlay_cfg = config.get("overlay", {})
    if not bool(overlay_cfg.get("enabled", True)):
        return 0

    try:
        import tkinter as tk
    except Exception as exc:
        print(f"Overlay could not start because tkinter is unavailable: {exc}", flush=True)
        return 2

    monitor_heartbeat = resolve_config_path(config, config["watchdog"]["heartbeat_file"])
    watchdog_heartbeat = resolve_config_path(
        config,
        config["watchdog"].get("watchdog_heartbeat_file", "runtime/watchdog_heartbeat.json"),
    )
    supervisor_heartbeat = resolve_config_path(
        config,
        config["watchdog"].get("supervisor_heartbeat_file", "runtime/supervisor_heartbeat.json"),
    )
    quit_path = quit_signal_path(config)
    warning_seconds = max(1.0, float(overlay_cfg.get("warning_seconds", 6)))
    stale_seconds = max(warning_seconds + 1.0, float(overlay_cfg.get("stale_seconds", 14)))
    interval_ms = max(100, int(overlay_cfg.get("update_interval_ms", 250)))
    opacity = max(0.25, min(1.0, float(overlay_cfg.get("opacity", 0.86))))
    font_size = max(8, int(overlay_cfg.get("font_size", 10)))
    start_x = int(overlay_cfg.get("x", 320))
    start_y = int(overlay_cfg.get("y", 48))
    parent_pid = configured_parent_pid(config)
    volume_max = 250
    volume_warn = 25
    system_volume_check_ms = 1000
    layout = overlay_control_layout()
    full_height = int(layout["full_height"])
    collapsed_height = int(layout["collapsed_height"])
    softened = 0.25
    meter_green = blend_hex_color("#24d15d", "#10151b", softened)
    meter_yellow = blend_hex_color("#ffd43b", "#10151b", softened)
    meter_red = blend_hex_color("#ff3b30", "#10151b", softened)

    root = tk.Tk()
    root.title("Maple Alert Health")
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", opacity)
    root.configure(bg="#111418")
    root.geometry(f"{OVERLAY_WIDTH}x{full_height}+{start_x}+{start_y}")

    canvas = tk.Canvas(root, width=OVERLAY_WIDTH, height=full_height, bg="#111418", highlightthickness=0)
    canvas.pack(fill="both", expand=True)
    outer_bg = canvas.create_rectangle(0, 0, OVERLAY_WIDTH - 1, full_height - 1, fill="#111418", outline="#2b323b")
    health_bg = canvas.create_rectangle(0, 0, OVERLAY_WIDTH - 1, OVERLAY_HEALTH_HEIGHT, fill="#111418", outline="#2b323b")
    dot = canvas.create_oval(10, 11, 22, 23, fill="#24d15d", outline="")
    notify_box = layout["notify_button"]
    notify_button = canvas.create_rectangle(*notify_box, fill="#151d27", outline="#3b4654")
    notify_label = canvas.create_text(
        (notify_box[0] + notify_box[2]) // 2,
        (notify_box[1] + notify_box[3]) // 2,
        anchor="center",
        fill="#c7d2e0",
        font=("Consolas", max(7, font_size - 3), "bold"),
        text="DM",
    )
    min_box = layout["minimize_button"]["box"]
    minimize_button = canvas.create_rectangle(*min_box, fill="#17221b", outline="#3b704d")
    minimize_label = canvas.create_text(
        (min_box[0] + min_box[2]) // 2,
        (min_box[1] + min_box[3]) // 2,
        anchor="center",
        fill="#bdf7ce",
        font=("Consolas", max(8, font_size - 2), "bold"),
        text=str(layout["minimize_button"]["label_expanded"]),
    )
    quit_button = canvas.create_rectangle(320, 5, 336, 21, fill="#25171a", outline="#70404a")
    quit_label = canvas.create_text(
        328,
        13,
        anchor="center",
        fill="#ff9aa8",
        font=("Consolas", max(8, font_size - 2), "bold"),
        text="X",
    )
    label = canvas.create_text(
        32,
        17,
        anchor="w",
        fill="#d7fbe1",
        font=("Consolas", font_size, "bold"),
        text="LIVE |",
    )
    warning_layout = layout["volume_warning"]
    volume_warning_bg = canvas.create_rectangle(*warning_layout["bg"], fill="#151a20", outline="")
    volume_warning = canvas.create_text(
        *warning_layout["text"],
        anchor="w",
        fill="#aab4c0",
        font=("Consolas", max(8, font_size - 1), "bold"),
        text="SYSTEM VOL OK",
    )
    ignore_volume_button = canvas.create_rectangle(*warning_layout["button"], fill="#1b2430", outline="#3b4654")
    ignore_volume_label = canvas.create_text(
        *warning_layout["button_text"],
        anchor="center",
        fill="#aab4c0",
        font=("Consolas", max(8, font_size - 2), "bold"),
        text="IGNORE",
    )
    test_box = layout["test_button"]
    test_button = canvas.create_rectangle(*test_box, fill="#1b2430", outline="#3b4654")
    test_label = canvas.create_text(
        (test_box[0] + test_box[2]) // 2,
        (test_box[1] + test_box[3]) // 2,
        anchor="center",
        fill="#d7fbe1",
        font=("Consolas", max(8, font_size - 1), "bold"),
        text="TEST",
    )
    lie_layout = layout["meters"]["captcha"]
    lie_meter_label = canvas.create_text(
        *lie_layout["label_pos"],
        anchor="w",
        fill="#aab4c0",
        font=("Consolas", max(7, font_size - 3), "bold"),
        text=str(lie_layout["label"]),
    )
    lie_meter_outline = canvas.create_rectangle(*lie_layout["outline"], fill="#10151b", outline="#3b4654")
    lie_meter_fill = canvas.create_rectangle(*lie_layout["fill"], fill=meter_green, outline="")
    lie_meter_text = canvas.create_text(
        *lie_layout["text"],
        anchor="center",
        fill="#f3fff6",
        font=("Consolas", max(8, font_size - 2), "bold"),
        text="200%",
    )
    player_layout = layout["meters"]["minimap_red"]
    player_meter_label = canvas.create_text(
        *player_layout["label_pos"],
        anchor="w",
        fill="#aab4c0",
        font=("Consolas", max(7, font_size - 3), "bold"),
        text=str(player_layout["label"]),
    )
    player_meter_outline = canvas.create_rectangle(*player_layout["outline"], fill="#10151b", outline="#3b4654")
    player_meter_fill = canvas.create_rectangle(*player_layout["fill"], fill=meter_green, outline="")
    player_meter_text = canvas.create_text(
        *player_layout["text"],
        anchor="center",
        fill="#f3fff6",
        font=("Consolas", max(8, font_size - 2), "bold"),
        text="200%",
    )

    drag_state = {"x": 0, "y": 0, "mode": "drag"}
    spinner = ["|", "/", "-", "\\"]
    frame = {"i": 0}
    state: dict[str, Any] = {
        "alert_volumes": {
            "captcha": read_alert_volume_percent(config, kind="captcha"),
            "minimap_red": read_alert_volume_percent(config, kind="minimap_red"),
        },
        "testing_kind": None,
        "test_thread_active": False,
        "ignore_system_volume_warning": read_ignore_system_volume_warning(config),
        "system_volume": SystemVolumeState(None, None, None),
        "last_system_volume_check": 0.0,
        "last_capture_key": None,
        "resolution_notice": "",
        "resolution_notice_until": 0.0,
        "minimized": False,
        "current_height": full_height,
        "notification_dialog": None,
    }
    drawer_items = [
        volume_warning_bg,
        volume_warning,
        ignore_volume_button,
        ignore_volume_label,
        test_button,
        test_label,
        lie_meter_label,
        lie_meter_outline,
        lie_meter_fill,
        lie_meter_text,
        player_meter_label,
        player_meter_outline,
        player_meter_fill,
        player_meter_text,
    ]

    def age_text(age: float | None) -> str:
        if age is None:
            return "--"
        if age < 10:
            return f"{age:.1f}"
        return f"{age:.0f}"

    def point_in_box(x: int, y: int, box: tuple[int, int, int, int]) -> bool:
        return box[0] <= x <= box[2] and box[1] <= y <= box[3]

    def set_drawer_items_visible(visible: bool) -> None:
        item_state = "normal" if visible else "hidden"
        for item in drawer_items:
            canvas.itemconfigure(item, state=item_state)
        if visible:
            draw_system_volume_button()

    def apply_overlay_height(height: int) -> None:
        height = max(collapsed_height, min(full_height, int(height)))
        state["current_height"] = height
        root.geometry(f"{OVERLAY_WIDTH}x{height}+{root.winfo_x()}+{root.winfo_y()}")
        canvas.configure(height=height)
        canvas.coords(outer_bg, 0, 0, OVERLAY_WIDTH - 1, max(OVERLAY_HEALTH_HEIGHT, height - 1))

    def animate_drawer() -> None:
        target = overlay_drawer_target_height(bool(state.get("minimized", False)))
        current = int(state.get("current_height", full_height))
        if current == target:
            set_drawer_items_visible(target > collapsed_height)
            return
        if target > current:
            set_drawer_items_visible(True)
            next_height = min(target, current + 12)
        else:
            next_height = max(target, current - 12)
        apply_overlay_height(next_height)
        if next_height == target:
            set_drawer_items_visible(target > collapsed_height)
            return
        root.after(16, animate_drawer)

    def toggle_minimized() -> None:
        minimized = not bool(state.get("minimized", False))
        state["minimized"] = minimized
        canvas.itemconfigure(
            minimize_label,
            text=str(
                layout["minimize_button"]["label_collapsed"]
                if minimized
                else layout["minimize_button"]["label_expanded"]
            ),
        )
        animate_drawer()

    def on_press(event: Any) -> None:
        event_x = int(event.x)
        event_y = int(event.y)
        if point_in_box(event_x, event_y, tuple(layout["quit_button"])):
            drag_state["mode"] = "quit"
            return
        if point_in_box(event_x, event_y, tuple(layout["notify_button"])):
            drag_state["mode"] = "notify"
            return
        if point_in_box(event_x, event_y, tuple(layout["minimize_button"]["box"])):
            drag_state["mode"] = "minimize"
            return
        if bool(state.get("minimized", False)):
            drag_state["x"] = event_x
            drag_state["y"] = event_y
            drag_state["mode"] = "drag"
            return
        if point_in_box(event_x, event_y, tuple(warning_layout["button"])):
            if bool(state.get("system_volume_button_visible", False)):
                drag_state["mode"] = "ignore_volume"
                return
        if point_in_box(event_x, event_y, tuple(lie_layout["outline"])):
            drag_state["mode"] = "volume_captcha"
            update_alert_volume_from_x(event_x, "captcha")
            return
        if point_in_box(event_x, event_y, tuple(player_layout["outline"])):
            drag_state["mode"] = "volume_minimap_red"
            update_alert_volume_from_x(event_x, "minimap_red")
            return
        if point_in_box(event_x, event_y, tuple(test_box)):
            drag_state["mode"] = "test"
            return
        drag_state["x"] = event_x
        drag_state["y"] = event_y
        drag_state["mode"] = "drag"

    def on_drag(event: Any) -> None:
        if drag_state.get("mode") == "volume_captcha":
            update_alert_volume_from_x(int(event.x), "captcha")
            return
        if drag_state.get("mode") == "volume_minimap_red":
            update_alert_volume_from_x(int(event.x), "minimap_red")
            return
        if drag_state.get("mode") == "ignore_volume":
            return
        if drag_state.get("mode") == "quit":
            return
        if drag_state.get("mode") == "notify":
            return
        if drag_state.get("mode") == "minimize":
            return
        if drag_state.get("mode") == "test":
            return
        x = root.winfo_x() + int(event.x) - drag_state["x"]
        y = root.winfo_y() + int(event.y) - drag_state["y"]
        root.geometry(f"+{x}+{y}")

    def on_release(_: Any) -> None:
        if drag_state.get("mode") == "quit":
            request_full_quit()
            drag_state["mode"] = "drag"
            return
        if drag_state.get("mode") == "notify":
            open_notification_settings_dialog()
            drag_state["mode"] = "drag"
            return
        if drag_state.get("mode") == "minimize":
            toggle_minimized()
            drag_state["mode"] = "drag"
            return
        if drag_state.get("mode") == "ignore_volume":
            toggle_system_volume_warning()
        if drag_state.get("mode") == "test":
            play_test_alert_sound()
        drag_state["mode"] = "drag"

    def request_full_quit() -> None:
        try:
            request_quit(config, "overlay")
            print(f"Quit requested from overlay. Signal written to {quit_path}", flush=True)
        except Exception as exc:
            print(f"Could not write quit request: {exc}", flush=True)
        root.destroy()

    def notification_entry_value(settings: dict[str, Any], service: str, key: str) -> str:
        service_settings = settings.get(service, {})
        if isinstance(service_settings, dict) and service_settings.get(key) is not None:
            return str(service_settings.get(key, ""))
        return str(config.get(service, {}).get(key, ""))

    def open_notification_settings_dialog() -> None:
        existing = state.get("notification_dialog")
        try:
            if existing is not None and existing.winfo_exists():
                existing.lift()
                return
        except Exception:
            pass

        settings = read_notification_settings(config)
        dialog = tk.Toplevel(root)
        state["notification_dialog"] = dialog
        dialog.title("Maple Alert Notifications")
        dialog.configure(bg="#111418")
        dialog.attributes("-topmost", True)
        dialog.resizable(False, False)
        dialog.geometry(f"+{root.winfo_x()}+{root.winfo_y() + int(state.get('current_height', full_height)) + 8}")

        remote_var = tk.BooleanVar(value=remote_notifications_enabled(config))
        telegram_settings = settings.get("telegram", {})
        discord_settings = settings.get("discord", {})
        telegram_enabled_var = tk.BooleanVar(
            value=bool(
                telegram_settings.get(
                    "enabled",
                    config.get("alerts", {}).get("telegram_enabled", False),
                )
            )
        )
        discord_enabled_var = tk.BooleanVar(
            value=bool(discord_settings.get("enabled", config.get("discord", {}).get("enabled", False)))
        )
        entries: dict[str, tk.Entry] = {}

        def add_label(text: str, row: int, column: int = 0, columnspan: int = 1) -> None:
            tk.Label(
                dialog,
                text=text,
                bg="#111418",
                fg="#d7fbe1",
                font=("Consolas", 9, "bold"),
            ).grid(row=row, column=column, columnspan=columnspan, sticky="w", padx=10, pady=(8, 2))

        def add_entry(service: str, key: str, row: int, label_text: str, show: str = "") -> None:
            add_label(label_text, row)
            entry = tk.Entry(
                dialog,
                width=38,
                bg="#10151b",
                fg="#f3fff6",
                insertbackground="#f3fff6",
                relief="flat",
                show=show,
                font=("Consolas", 9),
            )
            entry.insert(0, notification_entry_value(settings, service, key))
            entry.grid(row=row, column=1, padx=10, pady=(8, 2))
            entries[f"{service}.{key}"] = entry

        tk.Checkbutton(
            dialog,
            text="ENABLE REMOTE ALERTS",
            variable=remote_var,
            bg="#111418",
            fg="#fff2b0",
            activebackground="#111418",
            activeforeground="#fff2b0",
            selectcolor="#332b0e",
            font=("Consolas", 9, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 2))

        tk.Checkbutton(
            dialog,
            text="TELEGRAM",
            variable=telegram_enabled_var,
            bg="#111418",
            fg="#aab4c0",
            activebackground="#111418",
            activeforeground="#d7fbe1",
            selectcolor="#17221b",
            font=("Consolas", 9, "bold"),
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=10, pady=(6, 0))
        add_entry("telegram", "bot_token", 2, "Bot token", "*")
        add_entry("telegram", "chat_id", 3, "Chat ID")

        tk.Checkbutton(
            dialog,
            text="DISCORD",
            variable=discord_enabled_var,
            bg="#111418",
            fg="#aab4c0",
            activebackground="#111418",
            activeforeground="#d7fbe1",
            selectcolor="#17221b",
            font=("Consolas", 9, "bold"),
        ).grid(row=4, column=0, columnspan=2, sticky="w", padx=10, pady=(8, 0))
        add_entry("discord", "bot_token", 5, "Bot token", "*")
        add_entry("discord", "user_id", 6, "User ID")
        add_entry("discord", "webhook_url", 7, "Webhook URL")

        status_var = tk.StringVar(value="")
        status_label = tk.Label(
            dialog,
            textvariable=status_var,
            bg="#111418",
            fg="#aab4c0",
            font=("Consolas", 8, "bold"),
        )
        status_label.grid(row=8, column=0, columnspan=2, sticky="w", padx=10, pady=(8, 0))

        def collect_payload() -> dict[str, Any]:
            return {
                "remote_enabled": bool(remote_var.get()),
                "telegram": {
                    "enabled": bool(telegram_enabled_var.get()),
                    "bot_token": entries["telegram.bot_token"].get().strip(),
                    "chat_id": entries["telegram.chat_id"].get().strip(),
                },
                "discord": {
                    "enabled": bool(discord_enabled_var.get()),
                    "bot_token": entries["discord.bot_token"].get().strip(),
                    "user_id": entries["discord.user_id"].get().strip(),
                    "webhook_url": entries["discord.webhook_url"].get().strip(),
                },
            }

        def save_settings() -> None:
            write_notification_settings(config, collect_payload())
            status_var.set("Saved")

        def test_settings() -> None:
            write_notification_settings(config, collect_payload())
            status_var.set("Sending test...")

            def worker() -> None:
                logger = logging.getLogger("maple_alert_overlay_notify")
                logger.addHandler(logging.NullHandler())
                sent_telegram = send_telegram_notification(
                    config,
                    logger,
                    f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Maple Alert test: Telegram notifications are configured.",
                )
                sent_discord = send_discord_notification(
                    config,
                    logger,
                    f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Maple Alert test: Discord notifications are configured.",
                )
                result = "Test sent" if (sent_telegram or sent_discord) else "Nothing sent; check IDs/tokens"
                try:
                    dialog.after(0, lambda: status_var.set(result))
                except Exception:
                    pass

            threading.Thread(target=worker, daemon=True).start()

        button_frame = tk.Frame(dialog, bg="#111418")
        button_frame.grid(row=9, column=0, columnspan=2, sticky="e", padx=10, pady=10)
        for text, command in (("SAVE", save_settings), ("TEST", test_settings), ("CLOSE", dialog.destroy)):
            tk.Button(
                button_frame,
                text=text,
                command=command,
                bg="#1b2430",
                fg="#d7fbe1",
                activebackground="#243244",
                activeforeground="#ffffff",
                relief="flat",
                font=("Consolas", 8, "bold"),
                padx=10,
            ).pack(side="left", padx=4)

    def toggle_system_volume_warning() -> None:
        ignored = not bool(state.get("ignore_system_volume_warning", False))
        state["ignore_system_volume_warning"] = ignored
        write_ignore_system_volume_warning(config, ignored)
        draw_system_volume_button()

    def update_alert_volume_from_x(x: int, kind: str) -> None:
        meter = layout["meters"][kind]
        ratio = max(0.0, min(1.0, (x - int(meter["fill_left"])) / float(meter["fill_width"])))
        percent = int(round(ratio * volume_max / 5.0) * 5)
        volumes = state["alert_volumes"]
        volumes[kind] = max(0, min(volume_max, percent))
        write_alert_volume_percent(config, int(volumes[kind]), kind=kind)
        draw_volume_controls()

    def play_test_alert_sound() -> None:
        if bool(state.get("test_thread_active", False)):
            return
        state["test_thread_active"] = True
        state["testing_kind"] = "captcha"
        draw_volume_controls()

        def worker() -> None:
            try:
                for kind in ("captcha", "minimap_red"):
                    state["testing_kind"] = kind
                    volume = read_alert_volume_percent(config, kind=kind)
                    play_alert_sound_pattern(kind, volume)
            finally:
                state["testing_kind"] = None
                state["test_thread_active"] = False

        threading.Thread(target=worker, daemon=True).start()

    def refresh_system_volume_if_needed() -> None:
        now = time.monotonic()
        if now - float(state.get("last_system_volume_check", 0.0)) < system_volume_check_ms / 1000.0:
            return
        state["system_volume"] = read_system_volume_state()
        state["last_system_volume_check"] = now

    def draw_one_volume_control(
        kind: str,
        label_obj: int,
        outline_obj: int,
        fill_obj: int,
        text_obj: int,
        fill_left: int,
        fill_top: int,
        fill_bottom: int,
        fill_width: int,
    ) -> bool:
        percent = int(state["alert_volumes"][kind])
        ratio = max(0.0, min(1.0, percent / float(volume_max)))
        fill_right = fill_left + int(round(fill_width * ratio))
        volume_low = percent < volume_warn
        testing = state.get("testing_kind") == kind
        if testing:
            fill_color = meter_yellow
            outline = "#ffe066"
            text_color = "#fff7c2"
            label_color = "#fff2b0"
            bg_fill = "#2d270f"
        elif volume_low:
            fill_color = meter_red
            outline = "#ff6b60"
            text_color = "#ffe3e0"
            label_color = "#ffb0aa"
            bg_fill = "#241315"
        else:
            fill_color = meter_green if percent >= 90 else meter_yellow
            outline = "#3b4654"
            text_color = "#f3fff6"
            label_color = "#aab4c0"
            bg_fill = "#10151b"
        canvas.coords(fill_obj, fill_left, fill_top, max(fill_left, fill_right), fill_bottom)
        canvas.itemconfigure(fill_obj, fill=fill_color)
        canvas.itemconfigure(outline_obj, outline=outline, fill=bg_fill)
        canvas.itemconfigure(text_obj, text=f"{percent}%", fill=text_color)
        canvas.itemconfigure(label_obj, fill=label_color)
        return volume_low

    def draw_volume_controls() -> None:
        lie_low = draw_one_volume_control(
            "captcha",
            lie_meter_label,
            lie_meter_outline,
            lie_meter_fill,
            lie_meter_text,
            int(lie_layout["fill_left"]),
            int(lie_layout["fill_top"]),
            int(lie_layout["fill_bottom"]),
            int(lie_layout["fill_width"]),
        )
        player_low = draw_one_volume_control(
            "minimap_red",
            player_meter_label,
            player_meter_outline,
            player_meter_fill,
            player_meter_text,
            int(player_layout["fill_left"]),
            int(player_layout["fill_top"]),
            int(player_layout["fill_bottom"]),
            int(player_layout["fill_width"]),
        )
        any_low = lie_low or player_low
        testing = state.get("testing_kind") is not None
        canvas.itemconfigure(
            test_button,
            fill="#2d270f" if testing else ("#331516" if any_low else "#1b2430"),
            outline="#ffe066" if testing else ("#ff6b60" if any_low else "#3b4654"),
        )
        canvas.itemconfigure(test_label, fill="#fff2b0" if testing else ("#ffe3e0" if any_low else "#d7fbe1"))

    def system_volume_message(volume_state: SystemVolumeState) -> str:
        if bool(state.get("ignore_system_volume_warning", False)):
            if volume_state.percent is not None:
                return f"SYSTEM VOL IGNORED {volume_state.percent}%"
            return "SYSTEM VOL IGNORED"
        if volume_state.muted is True:
            return "SYSTEM VOLUME MUTED"
        if volume_state.percent is not None and volume_state.percent < SYSTEM_VOLUME_WARNING_PERCENT:
            return f"SYSTEM VOLUME {volume_state.percent}% < {SYSTEM_VOLUME_WARNING_PERCENT}%"
        if volume_state.percent is not None:
            return f"SYSTEM VOL OK {volume_state.percent}%"
        return "SYSTEM VOL UNKNOWN"

    def read_monitor_heartbeat() -> dict[str, Any]:
        return read_json_file(monitor_heartbeat)

    def capture_size_from_heartbeat(payload: dict[str, Any]) -> tuple[int, int] | None:
        rect = payload.get("rect")
        if not isinstance(rect, dict):
            return None
        try:
            width = int(rect.get("width", 0))
            height = int(rect.get("height", 0))
        except (TypeError, ValueError):
            return None
        if width <= 0 or height <= 0:
            return None
        return width, height

    def maple_missing_from_heartbeat(payload: dict[str, Any], age: float | None) -> bool:
        if age is None or age > stale_seconds:
            return False
        if not bool(payload.get("target_window", config["capture"].get("target_window", False))):
            return False
        return payload.get("source") != "window"

    def alert_status_from_heartbeat(payload: dict[str, Any], age: float | None) -> dict[str, Any]:
        if age is None or age > stale_seconds:
            return {}
        status = payload.get("alert_status")
        return status if isinstance(status, dict) else {}

    def health_from_heartbeat(
        payload: dict[str, Any],
        age: float | None,
        key: str,
    ) -> dict[str, Any]:
        if age is None or age > stale_seconds:
            return {}
        health = payload.get(key)
        return health if isinstance(health, dict) else {}

    def active_alert_label(active_alert: str | None) -> str:
        if active_alert == "lie_detector":
            return "LIE DETECTOR ALERT"
        if active_alert == "player_detected":
            return "PLAYER DETECTED ALERT"
        return "ALERT"

    def refresh_capture_notice(payload: dict[str, Any]) -> None:
        size = capture_size_from_heartbeat(payload)
        if size is None:
            return
        source = str(payload.get("source", ""))
        key = (source, size[0], size[1])
        previous_key = state.get("last_capture_key")
        if previous_key is not None and previous_key != key:
            state["resolution_notice"] = f"DETECTED NEW RESOLUTION {size[0]}x{size[1]}"
            state["resolution_notice_until"] = time.monotonic() + 6.0
        state["last_capture_key"] = key

    def draw_system_volume_button(
        warning_active: bool | None = None,
        ignored: bool | None = None,
        pulse_on: bool = False,
    ) -> None:
        if warning_active is None:
            warning_active = bool(state.get("system_volume_button_visible", False))
        if ignored is None:
            ignored = bool(state.get("ignore_system_volume_warning", False))
        button_state = system_volume_button_state(warning_active, ignored, pulse_on)
        state["system_volume_button_visible"] = bool(button_state["visible"])
        item_state = "normal" if button_state["visible"] and not bool(state.get("minimized", False)) else "hidden"
        canvas.itemconfigure(ignore_volume_button, state=item_state)
        canvas.itemconfigure(ignore_volume_label, state=item_state)
        if not button_state["visible"]:
            return
        canvas.itemconfigure(
            ignore_volume_button,
            fill=button_state["fill"],
            outline=button_state["outline"],
        )
        canvas.itemconfigure(
            ignore_volume_label,
            text=button_state["label"],
            fill=button_state["label_fill"],
        )

    def update() -> None:
        if parent_pid and not process_is_alive(parent_pid):
            root.destroy()
            return

        refresh_system_volume_if_needed()
        monitor_age = heartbeat_age(monitor_heartbeat)
        watchdog_age = heartbeat_age(watchdog_heartbeat)
        supervisor_age = heartbeat_age(supervisor_heartbeat)
        monitor_payload = read_monitor_heartbeat()
        watchdog_payload = read_json_file(watchdog_heartbeat)
        supervisor_payload = read_json_file(supervisor_heartbeat)
        refresh_capture_notice(monitor_payload)
        maple_missing = maple_missing_from_heartbeat(monitor_payload, monitor_age)
        alert_status = alert_status_from_heartbeat(monitor_payload, monitor_age)
        monitor_health = health_from_heartbeat(watchdog_payload, watchdog_age, "monitor_health")
        supervisor_health = health_from_heartbeat(supervisor_payload, supervisor_age, "watchdog_health")
        watchdog_health = supervisor_health if supervisor_health.get("active") else monitor_health
        watchdog_health_active = bool(watchdog_health.get("active", False))
        active_alert = alert_status.get("active_alert")
        ages = [age for age in (monitor_age, watchdog_age, supervisor_age) if age is not None]
        worst_age = max(ages, default=None)
        system_volume = state["system_volume"]
        system_volume_ignored = bool(state.get("ignore_system_volume_warning", False))
        system_volume_needs_attention = (
            isinstance(system_volume, SystemVolumeState)
            and system_volume.needs_attention
        )
        if system_volume_ignored and not system_volume_needs_attention:
            system_volume_ignored = False
            state["ignore_system_volume_warning"] = False
            write_ignore_system_volume_warning(config, False)
        system_volume_bad = (
            system_volume_needs_attention
            and not system_volume_ignored
        )

        pulse_on = frame["i"] % 4 in (0, 1)
        if watchdog_health_active:
            status = "MONITOR"
            dot_color = "#ff3b30" if pulse_on else "#7a1815"
            text_color = "#ffe3e0"
            bg_color = "#451112" if pulse_on else "#111418"
        elif maple_missing:
            status = "NO MAPLE"
            dot_color = "#ff3b30" if pulse_on else "#7a1815"
            text_color = "#ffe3e0"
            bg_color = "#361112" if pulse_on else "#111418"
        elif active_alert:
            status = "ALERT"
            dot_color = "#ff3b30" if pulse_on else "#7a1815"
            text_color = "#ffe3e0"
            bg_color = "#451112" if pulse_on else "#111418"
        elif system_volume_bad:
            status = "VOL"
            dot_color = "#ffd43b" if pulse_on else "#806a16"
            text_color = "#fff2b0"
            bg_color = "#332b0e" if pulse_on else "#111418"
        elif worst_age is None or worst_age > stale_seconds:
            status = "STALE"
            dot_color = "#ff3b30"
            text_color = "#ffd5d2"
            bg_color = "#111418"
        elif worst_age > warning_seconds:
            status = "LATE"
            dot_color = "#ffd43b"
            text_color = "#fff2b0"
            bg_color = "#111418"
        else:
            status = "LIVE"
            dot_color = "#24d15d"
            text_color = "#d7fbe1"
            bg_color = "#111418"

        spin = spinner[frame["i"] % len(spinner)]
        frame["i"] += 1
        if watchdog_health_active:
            text = overlay_watchdog_health_text(watchdog_health, spin)
        elif maple_missing:
            text = f"MAPLE NOT DETECTED {spin}"
        elif active_alert:
            text = f"{active_alert_label(str(active_alert))} {spin}"
        elif system_volume_bad:
            text = f"{system_volume_message(system_volume)} {spin}"
        elif time.monotonic() < float(state.get("resolution_notice_until", 0.0)):
            text = f"{state.get('resolution_notice', '')} {spin}"
        else:
            text = overlay_live_status_text(alert_status, spin, time.time())
        warning_fill = "#3a2f0f" if system_volume_bad and pulse_on else "#151a20"
        warning_text = system_volume_message(system_volume)
        canvas.itemconfigure(dot, fill=dot_color)
        canvas.itemconfigure(label, fill=text_color, text=text)
        canvas.itemconfigure(health_bg, fill=bg_color)
        canvas.itemconfigure(volume_warning_bg, fill=warning_fill)
        canvas.itemconfigure(volume_warning, text=warning_text, fill="#fff2b0" if system_volume_bad else "#aab4c0")
        draw_system_volume_button(system_volume_needs_attention, system_volume_ignored, pulse_on)
        canvas.tag_raise(quit_button)
        canvas.tag_raise(quit_label)
        canvas.tag_raise(notify_button)
        canvas.tag_raise(notify_label)
        canvas.tag_raise(minimize_button)
        canvas.tag_raise(minimize_label)
        state["alert_volumes"]["captcha"] = read_alert_volume_percent(config, kind="captcha")
        state["alert_volumes"]["minimap_red"] = read_alert_volume_percent(config, kind="minimap_red")
        draw_volume_controls()
        root.attributes("-topmost", True)
        root.after(interval_ms, update)

    for widget in (root, canvas):
        widget.bind("<ButtonPress-1>", on_press)
        widget.bind("<B1-Motion>", on_drag)
        widget.bind("<ButtonRelease-1>", on_release)

    draw_volume_controls()
    update()
    root.mainloop()
    return 0


def run_test_image(config: dict[str, Any], args: argparse.Namespace) -> int:
    logger = setup_logging(config)
    detector = CaptchaDetector(config, logger)
    blue_block_crop_saver = make_blue_block_crop_saver(config, logger)

    image_path = Path(args.test_image).expanduser()
    if not image_path.is_absolute():
        image_path = Path.cwd() / image_path

    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None or image.size == 0:
        logger.error("Could not read test image: %s", image_path)
        return 2

    height, width = image.shape[:2]
    base_rect = Rect(0, 0, width, height)
    scale_info = set_runtime_scale(config, base_rect)
    captcha_rect = roi_to_rect(base_rect, config["roi"]["captcha"])
    minimap_rect = roi_to_rect(base_rect, config["roi"]["minimap"])

    captcha_bgr = crop_bgr(image, captcha_rect)
    minimap_bgr = crop_bgr(image, minimap_rect)
    captcha_result = detector.detect(captcha_bgr)
    minimap_result, minimap_mask = detect_minimap_red(minimap_bgr, config)
    lower_name = image_path.name.casefold()
    expected_captcha: bool | None = None
    if "noncaptcha" in lower_name:
        expected_captcha = False
    elif "captcha" in lower_name:
        expected_captcha = True

    save_debug_crops(config, captcha_bgr, minimap_bgr, minimap_mask, "test_image")
    blue_block_crop_path = blue_block_crop_saver.save(
        captcha_bgr,
        captcha_result.info.get("heuristic", {}).get("box"),
        "detected" if captcha_result.detected else "candidate",
    )

    print(
        json.dumps(
            {
                "test_image": str(image_path),
                "expected_captcha_from_filename": expected_captcha,
                "image_size": {"width": width, "height": height},
                "runtime_scale": scale_info.to_dict(),
                "captcha_roi": captcha_rect.__dict__,
                "minimap_roi": minimap_rect.__dict__,
                "captcha": {
                    "detected": captcha_result.detected,
                    "confidence": round(captcha_result.confidence, 4),
                    "info": captcha_result.info,
                },
                "minimap_red": {
                    "detected": minimap_result.detected,
                    "confidence": round(minimap_result.confidence, 4),
                    "info": minimap_result.info,
                },
                "debug_crops": str(resolve_config_path(config, config["debug"]["crop_dir"])),
                "blue_block_crop": str(blue_block_crop_path) if blue_block_crop_path else None,
            },
            indent=2,
        )
    )

    if expected_captcha is True and captcha_result.detected:
        logger.info("Test image passed: expected CAPTCHA and detector triggered")
    elif expected_captcha is True:
        logger.warning(
            "Test image failed: expected CAPTCHA but detector did not trigger. "
            "Check the saved CAPTCHA ROI crop first; if the prompt is visible there, "
            "loosen [detection.captcha] thresholds."
        )
    elif expected_captcha is False and captcha_result.detected:
        logger.warning(
            "Test image failed: expected non-CAPTCHA but detector triggered. "
            "Tighten [detection.captcha] thresholds or inspect the reported heuristic block."
        )
    elif expected_captcha is False:
        logger.info("Test image passed: expected non-CAPTCHA and detector stayed quiet")
    elif captcha_result.detected:
        logger.info("Test image detector triggered")
    else:
        logger.info("Test image did not trigger the CAPTCHA detector")
    return 0


def run(config: dict[str, Any], args: argparse.Namespace) -> int:
    started_at_epoch = time.time()
    if args.debug or args.calibrate:
        config["debug"]["enabled"] = True
        config["debug"]["show_windows"] = True
    if args.once:
        config["debug"]["save_crops"] = True

    logger = setup_logging(config)
    detector = CaptchaDetector(config, logger)
    alerts = AlertManager(config, logger)
    blue_block_crop_saver = make_blue_block_crop_saver(config, logger)
    red_dot_crop_saver = make_red_dot_crop_saver(config, logger)

    interval = capture_interval_seconds(config)
    fps = 1.0 / interval
    relocate_interval = max(0.5, float(config["capture"]["relocate_window_seconds"]))
    last_relocate = 0.0
    last_status = 0.0
    last_heartbeat = 0.0
    base_rect: Rect | None = None
    base_source = ""
    parent_pid = configured_parent_pid(config)

    logger.info(
        "Starting monitor fps=%.2f interval=%.2fs safe_mode=%s target_window=%s",
        fps,
        interval,
        config["alerts"]["safe_mode"],
        config["capture"]["target_window"],
    )
    logger.info("Monitor is running. Silence means no alert condition is currently detected.")

    with mss.MSS() as sct:
        while True:
            loop_start = time.monotonic()
            if quit_requested(config, started_at_epoch):
                logger.info("Quit request received; stopping monitor")
                print("Quit request received; stopping monitor.", flush=True)
                break

            if parent_pid and not process_is_alive(parent_pid):
                logger.info("Monitor parent pid=%s is gone; stopping monitor", parent_pid)
                break

            if base_rect is None or loop_start - last_relocate >= relocate_interval:
                new_rect, new_source = resolve_capture_rect(sct, config)
                if new_rect != base_rect or new_source != base_source:
                    previous_rect = base_rect
                    previous_source = base_source
                    scale_info = set_runtime_scale(config, new_rect)
                    logger.info(
                        "Capture source=%s rect=%s resolution=%sx%s scale_x=%.4f scale_y=%.4f pixel_scale=%.4f reference=%sx%s",
                        new_source,
                        new_rect,
                        new_rect.width,
                        new_rect.height,
                        scale_info.scale_x,
                        scale_info.scale_y,
                        scale_info.pixel_scale,
                        scale_info.reference_width,
                        scale_info.reference_height,
                    )
                    resolution_changed = (
                        previous_rect is not None
                        and (previous_rect.width, previous_rect.height) != (new_rect.width, new_rect.height)
                    )
                    source_changed = new_source != previous_source
                    if previous_rect is None:
                        status_line = (
                            f"Resolution {new_rect.width}x{new_rect.height} detected; "
                            f"capture_source={new_source}; "
                            f"pixel_scale={scale_info.pixel_scale:.4f}"
                        )
                    elif resolution_changed:
                        status_line = (
                            f"Detected new resolution {new_rect.width}x{new_rect.height}; "
                            f"capture_source={new_source}; "
                            f"pixel_scale={scale_info.pixel_scale:.4f}"
                        )
                    elif source_changed and new_source == "window":
                        status_line = (
                            f"Maple detected; window capture resolution {new_rect.width}x{new_rect.height}; "
                            f"pixel_scale={scale_info.pixel_scale:.4f}"
                        )
                    elif source_changed and new_source == "monitor":
                        status_line = (
                            f"Maple not detected; monitor fallback resolution {new_rect.width}x{new_rect.height}; "
                            f"pixel_scale={scale_info.pixel_scale:.4f}"
                        )
                    else:
                        status_line = (
                            f"Capture resolution {new_rect.width}x{new_rect.height}; "
                            f"capture_source={new_source}; "
                            f"pixel_scale={scale_info.pixel_scale:.4f}"
                        )
                    print(
                        (
                            f"{status_line}; "
                            f"scale_x={scale_info.scale_x:.4f} "
                            f"scale_y={scale_info.scale_y:.4f}"
                        ),
                        flush=True,
                    )
                    if new_source == "monitor" and config["capture"]["target_window"]:
                        print(
                            (
                                "Maple not detected; monitor fallback is active. "
                                "The overlay will flash red until the Maple window is found."
                            ),
                            flush=True,
                        )
                        logger.warning(
                            "Maple window title '%s' was not found; falling back to monitor_index=%s. "
                            "Run 'MapleAlert.exe --list-windows' and copy the visible title into config.toml if needed.",
                            config["capture"]["window_title"],
                            config["capture"]["monitor_index"],
                        )
                base_rect = new_rect
                base_source = new_source
                last_relocate = loop_start

            captcha_rect = roi_to_rect(base_rect, config["roi"]["captcha"])
            minimap_rect = roi_to_rect(base_rect, config["roi"]["minimap"])

            captcha_bgr = grab_bgr(sct, captcha_rect)
            minimap_bgr = grab_bgr(sct, minimap_rect)

            captcha_result = detector.detect(captcha_bgr)
            minimap_result, minimap_mask = detect_minimap_red(minimap_bgr, config)

            captcha_alert_fired = alerts.handle_result("captcha", captcha_result)
            minimap_alert_fired = alerts.handle_result("minimap_red", minimap_result)
            if captcha_alert_fired:
                blue_block_crop_saver.save(
                    captcha_bgr,
                    captcha_result.info.get("heuristic", {}).get("box"),
                    "alert",
                )
            if minimap_alert_fired:
                red_dot_crop_saver.save(
                    minimap_bgr,
                    minimap_result.info.get("largest_blob_box"),
                    "alert",
                )

            status_interval = max(0.0, float(config["alerts"].get("status_interval_seconds", 15)))
            if status_interval > 0 and loop_start - last_status >= status_interval:
                log_monitor_status(
                    logger,
                    base_source,
                    base_rect,
                    captcha_result,
                    minimap_result,
                    alerts.minimap_seen_since,
                    config.get("_runtime_scale", {}),
                )
                last_status = loop_start

            heartbeat_interval = max(
                0.5,
                float(config["watchdog"].get("heartbeat_interval_seconds", 2)),
            )
            if loop_start - last_heartbeat >= heartbeat_interval:
                write_heartbeat(config, base_source, base_rect, alerts.status_snapshot())
                last_heartbeat = loop_start

            if config["debug"]["save_crops"] and (captcha_result.detected or minimap_result.detected or args.once):
                suffix = "detected" if captcha_result.detected or minimap_result.detected else "sample"
                save_debug_crops(config, captcha_bgr, minimap_bgr, minimap_mask, suffix)

            if config["debug"]["show_windows"]:
                keep_running = show_debug_windows(
                    captcha_bgr,
                    minimap_bgr,
                    minimap_mask,
                    captcha_result,
                    minimap_result,
                )
                if not keep_running:
                    logger.info("Debug window closed by user")
                    break

            if args.once:
                print(
                    json.dumps(
                        {
                            "capture_source": base_source,
                            "capture_rect": base_rect.__dict__,
                            "runtime_scale": config.get("_runtime_scale", {}),
                            "captcha": {
                                "detected": captcha_result.detected,
                                "confidence": round(captcha_result.confidence, 4),
                                "info": captcha_result.info,
                            },
                            "minimap_red": {
                                "detected": minimap_result.detected,
                                "confidence": round(minimap_result.confidence, 4),
                                "info": minimap_result.info,
                            },
                        },
                        indent=2,
                    )
                )
                break

            elapsed = time.monotonic() - loop_start
            time.sleep(max(0.0, interval - elapsed))

    cv2.destroyAllWindows()
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Local visual alert monitor for CAPTCHA and minimap red markers."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {APP_VERSION}")
    parser.add_argument("--config", default="config.toml", help="Path to config TOML file.")
    parser.add_argument("--debug", action="store_true", help="Show live ROI debug windows.")
    parser.add_argument(
        "--calibrate",
        action="store_true",
        help="Show live ROI debug windows for threshold tuning. Press q or Esc to quit.",
    )
    parser.add_argument("--once", action="store_true", help="Capture one frame, save debug crops, and print stats.")
    parser.add_argument(
        "--test-image",
        help="Run detection once against an image file instead of live screen capture.",
    )
    parser.add_argument(
        "--watchdog",
        action="store_true",
        help="Run a watchdog wrapper that alerts and restarts the monitor if it exits or stops writing heartbeats.",
    )
    parser.add_argument(
        "--overlay",
        action="store_true",
        help="Show a small always-on-top heartbeat overlay.",
    )
    parser.add_argument(
        "--export-alert-wavs",
        nargs="?",
        const="alert_sounds",
        metavar="DIR",
        help="Write the generated alert WAV files to DIR, or alert_sounds if DIR is omitted.",
    )
    parser.add_argument(
        "--setup-check",
        action="store_true",
        help="Print a redacted readiness report for folder files, target window, audio, volumes, and remote alerts.",
    )
    parser.add_argument(
        "--diagnostics",
        action="store_true",
        help="Write a redacted text/JSON diagnostics bundle for support.",
    )
    parser.add_argument(
        "--diagnostics-dir",
        default="runtime/diagnostics",
        help="Directory for --diagnostics output. Defaults to runtime/diagnostics beside config.toml.",
    )
    parser.add_argument(
        "--validate-config",
        action="store_true",
        help="Check config values and print redacted errors/warnings.",
    )
    parser.add_argument(
        "--build-info",
        action="store_true",
        help="Print app version and release manifest metadata as JSON.",
    )
    parser.add_argument(
        "--parent-pid",
        type=int,
        default=0,
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--list-windows", action="store_true", help="Print visible window titles and rectangles.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.list_windows:
        print_window_list()
        return 0

    config_path = Path(args.config).expanduser()
    if args.config == "config.toml" and getattr(sys, "frozen", False):
        config_path = Path(sys.executable).resolve().with_name("config.toml")
    if args.build_info:
        if getattr(sys, "frozen", False):
            base_dir = Path(sys.executable).resolve().parent
        else:
            base_dir = config_path.resolve().parent
        return run_build_info(base_dir)
    config = load_config(config_path)
    config["_parent_pid"] = int(getattr(args, "parent_pid", 0) or 0)
    if args.setup_check:
        return run_setup_check(config, config_path.resolve())
    if args.diagnostics:
        return run_diagnostics(config, config_path.resolve(), args.diagnostics_dir)
    if args.validate_config:
        return run_validate_config(config)
    if args.export_alert_wavs:
        return export_alert_wavs(config, args.export_alert_wavs)
    if args.overlay:
        return run_overlay(config)
    if args.watchdog:
        return run_watchdog(config, config_path.resolve())
    if args.test_image:
        return run_test_image(config, args)
    return run(config, args)


if __name__ == "__main__":
    raise SystemExit(main())
