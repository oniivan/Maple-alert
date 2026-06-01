from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from maple_alert import (  # noqa: E402
    DEFAULT_CONFIG,
    FREE_MARKET_EXIT_FAILED_WARNING,
    FREE_MARKET_FORCE_CLOSED_MESSAGE,
    FreeMarketExitController,
)
from vision_core import DetectionResult  # noqa: E402


def make_config() -> dict:
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["free_market_exit"]["enabled"] = True
    config["free_market_exit"]["countdown_seconds"] = 10
    config["free_market_exit"]["reset_after_clear_seconds"] = 12
    config["free_market_exit"]["trigger_after_captcha_clear_seconds"] = 20
    return config


def result(detected: bool) -> DetectionResult:
    return DetectionResult(detected, 1.0 if detected else 0.0, {})


def test_cancel_waits_until_free_market_has_cleared_long_enough() -> None:
    controller = FreeMarketExitController(make_config())

    assert controller.update(result(False), now=0.0, target_pid=123, captcha_detected=True).action is None
    assert controller.update(result(True), now=1.0, target_pid=123, captcha_detected=False).action == "show_prompt"
    controller.cancel(now=2.0)

    assert controller.update(result(True), now=6.0, target_pid=123, captcha_detected=False).action is None
    assert controller.update(result(False), now=10.0, target_pid=123, captcha_detected=False).action is None
    assert controller.update(result(False), now=21.9, target_pid=123, captcha_detected=False).action is None
    assert controller.update(result(False), now=22.0, target_pid=123, captcha_detected=False).action == "reset"
    assert controller.update(result(True), now=24.0, target_pid=123, captcha_detected=False).action is None


def test_countdown_expiry_requests_exit_once() -> None:
    controller = FreeMarketExitController(make_config())

    assert controller.update(result(False), now=0.0, target_pid=123, captcha_detected=True).action is None
    shown = controller.update(result(True), now=1.0, target_pid=123, captcha_detected=False)
    assert shown.action == "show_prompt"
    assert shown.seconds_left == 10
    assert controller.update(result(True), now=1.9, target_pid=123, captcha_detected=False).seconds_left == 10
    assert controller.update(result(True), now=10.9, target_pid=123, captcha_detected=False).action is None
    assert controller.update(result(True), now=11.0, target_pid=123, captcha_detected=False).action == "exit"
    assert controller.update(result(True), now=12.0, target_pid=123, captcha_detected=False).action is None


def test_free_market_only_triggers_inside_post_captcha_clear_window() -> None:
    controller = FreeMarketExitController(make_config())

    assert controller.update(result(True), now=0.0, target_pid=123, captcha_detected=False).action is None
    assert controller.update(result(True), now=1.0, target_pid=123, captcha_detected=True).action is None
    assert controller.update(result(True), now=2.0, target_pid=123, captcha_detected=False).action == "show_prompt"

    controller = FreeMarketExitController(make_config())
    assert controller.update(result(False), now=0.0, target_pid=123, captcha_detected=True).action is None
    assert controller.update(result(False), now=1.0, target_pid=123, captcha_detected=False).action is None
    assert controller.update(result(True), now=21.1, target_pid=123, captcha_detected=False).action is None


def test_explicit_test_request_bypasses_post_captcha_gate() -> None:
    controller = FreeMarketExitController(make_config())

    decision = controller.update(result(False), now=0.0, target_pid=123, test_requested=True)

    assert decision.action == "show_prompt"
    assert decision.seconds_left == 10


def test_explicit_test_request_keeps_countdown_without_free_market_detection() -> None:
    controller = FreeMarketExitController(make_config())

    assert controller.update(result(False), now=0.0, target_pid=123, test_requested=True).action == "show_prompt"
    still_counting = controller.update(result(False), now=2.0, target_pid=123)
    assert still_counting.action is None
    assert still_counting.seconds_left == 8
    assert controller.update(result(False), now=9.9, target_pid=123).action is None
    assert controller.update(result(False), now=10.0, target_pid=123).action == "exit"


def test_explicit_test_request_can_retrigger_after_failed_exit_state() -> None:
    controller = FreeMarketExitController(make_config())

    assert controller.update(result(False), now=0.0, target_pid=None, test_requested=True).action == "show_prompt"
    assert controller.update(result(False), now=10.0, target_pid=None).action == "exit"
    controller.report_failure("FAILED TO EXIT MSW.EXE! missing target pid", now_epoch=10.0)

    decision = controller.update(result(False), now=11.0, target_pid=None, test_requested=True)

    assert decision.action == "show_prompt"
    assert decision.seconds_left == 10


def test_real_detection_can_retrigger_after_failed_exit_state() -> None:
    controller = FreeMarketExitController(make_config())

    assert controller.update(result(False), now=0.0, target_pid=None, captcha_detected=True).action is None
    assert controller.update(result(True), now=1.0, target_pid=None, captcha_detected=False).action == "show_prompt"
    assert controller.update(result(True), now=11.0, target_pid=None, captcha_detected=False).action == "exit"
    controller.report_failure("FAILED TO EXIT MSW.EXE! missing target pid", now_epoch=11.0)

    assert controller.update(result(False), now=12.0, target_pid=123, captcha_detected=True).action is None
    decision = controller.update(result(True), now=13.0, target_pid=123, captcha_detected=False)

    assert decision.action == "show_prompt"
    assert decision.seconds_left == 10
    assert controller.target_pid == 123


def test_failed_exit_state_does_not_restart_from_same_stale_detection() -> None:
    controller = FreeMarketExitController(make_config())

    assert controller.update(result(False), now=0.0, target_pid=None, captcha_detected=True).action is None
    assert controller.update(result(True), now=1.0, target_pid=None, captcha_detected=False).action == "show_prompt"
    assert controller.update(result(True), now=11.0, target_pid=None, captcha_detected=False).action == "exit"
    controller.report_failure("FAILED TO EXIT MSW.EXE! missing target pid", now_epoch=11.0)

    assert controller.update(result(True), now=12.0, target_pid=None, captcha_detected=False).action is None
    assert controller.update(result(True), now=19.0, target_pid=None, captcha_detected=False).action is None


def test_free_market_prompt_messages_match_safeguard_copy() -> None:
    assert FREE_MARKET_FORCE_CLOSED_MESSAGE == (
        "Detected a move to free market\n"
        "due to a possible missed captcha.\n\n"
        "SAFEGUARD: Force-closed the game."
    )
    assert FREE_MARKET_EXIT_FAILED_WARNING == "WARNING: msw.exe was not detected, unable to close the game!"


if __name__ == "__main__":
    test_cancel_waits_until_free_market_has_cleared_long_enough()
    test_countdown_expiry_requests_exit_once()
    test_free_market_only_triggers_inside_post_captcha_clear_window()
    test_explicit_test_request_bypasses_post_captcha_gate()
    test_explicit_test_request_keeps_countdown_without_free_market_detection()
    test_explicit_test_request_can_retrigger_after_failed_exit_state()
    test_real_detection_can_retrigger_after_failed_exit_state()
    test_failed_exit_state_does_not_restart_from_same_stale_detection()
    test_free_market_prompt_messages_match_safeguard_copy()
    print("free market exit flow tests passed")
