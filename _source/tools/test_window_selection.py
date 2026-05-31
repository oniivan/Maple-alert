from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import maple_alert  # noqa: E402
from maple_alert import (  # noqa: E402
    Rect,
    WindowInfo,
    find_target_window,
    find_window_rect,
    ignored_window_title_substrings,
    is_ignored_window_title,
)


def test_own_console_title_is_ignored_by_default() -> None:
    ignored = ignored_window_title_substrings({})

    assert is_ignored_window_title("Maple Alert", ignored)
    assert is_ignored_window_title("Maple Alert Health", ignored)
    assert is_ignored_window_title("Administrator: Maple Alert", ignored)
    assert is_ignored_window_title("Downloads - File Explorer", ignored)
    assert is_ignored_window_title("oniivan/Maple-alert: Lightweight Windows visual alert tool for Maple. - Google Chrome", ignored)


def test_find_window_skips_own_alert_windows(monkeypatch=None) -> None:
    windows = [
        ("Maple Alert", Rect(10, 10, 700, 400)),
        ("Maple Alert Health", Rect(30, 30, 360, 160)),
        ("Downloads - File Explorer", Rect(40, 40, 1139, 426)),
        ("oniivan/Maple-alert: Lightweight Windows visual alert tool for Maple. - Google Chrome", Rect(50, 50, 1550, 830)),
        ("Maple Client", Rect(100, 100, 1919, 1079)),
    ]

    original = maple_alert.list_windows
    maple_alert.list_windows = lambda: windows
    try:
        rect = find_window_rect("Maple")
    finally:
        maple_alert.list_windows = original

    assert rect == Rect(100, 100, 1919, 1079)


def test_find_window_returns_none_when_only_own_alert_windows_match() -> None:
    windows = [
        ("Maple Alert", Rect(10, 10, 700, 400)),
        ("Maple Alert Health", Rect(30, 30, 360, 160)),
        ("Downloads - File Explorer", Rect(40, 40, 1139, 426)),
        ("oniivan/Maple-alert: Lightweight Windows visual alert tool for Maple. - Google Chrome", Rect(50, 50, 1550, 830)),
    ]

    original = maple_alert.list_windows
    maple_alert.list_windows = lambda: windows
    try:
        rect = find_window_rect("Maple")
    finally:
        maple_alert.list_windows = original

    assert rect is None


def test_target_window_prefers_matching_process_over_title_only_window() -> None:
    windows = [
        WindowInfo("Maple Alert", Rect(10, 10, 700, 400), hwnd=10, pid=100, exe_name="MapleAlert.exe"),
        WindowInfo("Maple Client", Rect(20, 20, 1200, 800), hwnd=20, pid=200, exe_name="notepad.exe"),
        WindowInfo("Odd Client", Rect(30, 30, 1919, 1079), hwnd=30, pid=300, exe_name="msw.exe"),
    ]

    original = maple_alert.list_window_infos
    maple_alert.list_window_infos = lambda: windows
    try:
        target = find_target_window(
            {
                "process_match_enabled": True,
                "process_names": ["msw.exe"],
                "title_fallback_enabled": True,
                "window_title": "Maple",
            }
        )
    finally:
        maple_alert.list_window_infos = original

    assert target is not None
    assert target.pid == 300
    assert target.match_source == "process"


def test_title_fallback_can_be_disabled() -> None:
    windows = [
        WindowInfo("Maple Client", Rect(20, 20, 1200, 800), hwnd=20, pid=200, exe_name="notepad.exe"),
    ]

    original = maple_alert.list_window_infos
    maple_alert.list_window_infos = lambda: windows
    try:
        target = find_target_window(
            {
                "process_match_enabled": True,
                "process_names": ["msw.exe"],
                "title_fallback_enabled": False,
                "window_title": "Maple",
            }
        )
    finally:
        maple_alert.list_window_infos = original

    assert target is None


if __name__ == "__main__":
    test_own_console_title_is_ignored_by_default()
    test_find_window_skips_own_alert_windows()
    test_find_window_returns_none_when_only_own_alert_windows_match()
    test_target_window_prefers_matching_process_over_title_only_window()
    test_title_fallback_can_be_disabled()
    print("window selection tests passed")
