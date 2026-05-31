from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from maple_alert import DEFAULT_CONFIG, FreeMarketExitController  # noqa: E402
from vision_core import DetectionResult  # noqa: E402


def make_config() -> dict:
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["free_market_exit"]["enabled"] = True
    config["free_market_exit"]["countdown_seconds"] = 15
    config["free_market_exit"]["reset_after_clear_seconds"] = 12
    return config


def result(detected: bool) -> DetectionResult:
    return DetectionResult(detected, 1.0 if detected else 0.0, {})


def test_cancel_waits_until_free_market_has_cleared_long_enough() -> None:
    controller = FreeMarketExitController(make_config())

    assert controller.update(result(True), now=0.0, target_pid=123).action == "show_prompt"
    controller.cancel(now=2.0)

    assert controller.update(result(True), now=6.0, target_pid=123).action is None
    assert controller.update(result(False), now=10.0, target_pid=123).action is None
    assert controller.update(result(False), now=21.9, target_pid=123).action is None
    assert controller.update(result(False), now=22.0, target_pid=123).action == "reset"
    assert controller.update(result(True), now=24.0, target_pid=123).action == "show_prompt"


def test_countdown_expiry_requests_exit_once() -> None:
    controller = FreeMarketExitController(make_config())

    assert controller.update(result(True), now=0.0, target_pid=123).action == "show_prompt"
    assert controller.update(result(True), now=14.9, target_pid=123).action is None
    assert controller.update(result(True), now=15.0, target_pid=123).action == "exit"
    assert controller.update(result(True), now=16.0, target_pid=123).action is None


if __name__ == "__main__":
    test_cancel_waits_until_free_market_has_cleared_long_enough()
    test_countdown_expiry_requests_exit_once()
    print("free market exit flow tests passed")
