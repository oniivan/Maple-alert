from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from maple_alert import quit_requested, request_quit


def test_quit_signal_ignores_stale_file() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        config = {
            "_config_dir": temp_dir,
            "watchdog": {"quit_file": "runtime/quit_requested.json"},
        }
        request_quit(config, "test")
        assert not quit_requested(config, time.time() + 10)


def test_quit_signal_is_seen_after_start() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        config = {
            "_config_dir": temp_dir,
            "watchdog": {"quit_file": "runtime/quit_requested.json"},
        }
        started_at = time.time() - 1
        request_quit(config, "test")
        assert quit_requested(config, started_at)


if __name__ == "__main__":
    test_quit_signal_ignores_stale_file()
    test_quit_signal_is_seen_after_start()
    print("quit signal tests passed")
