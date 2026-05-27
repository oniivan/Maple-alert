from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import maple_alert  # noqa: E402
from maple_alert import Rect, find_window_rect, ignored_window_title_substrings, is_ignored_window_title  # noqa: E402


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


if __name__ == "__main__":
    test_own_console_title_is_ignored_by_default()
    test_find_window_skips_own_alert_windows()
    test_find_window_returns_none_when_only_own_alert_windows_match()
    print("window selection tests passed")
