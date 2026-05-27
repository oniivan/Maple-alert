from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_repo_root_is_runnable_one_click_layout() -> None:
    required_root_files = [
        "START_MAPLE_ALERT.bat",
        "MapleAlert.exe",
        "config.toml",
        "README.md",
        "README_FIRST.txt",
    ]
    for relative_path in required_root_files:
        assert (ROOT / relative_path).is_file(), relative_path

    assert (ROOT / "_internal" / "watchdog_supervisor.ps1").is_file()
    assert (ROOT / "alert_sounds" / "captcha_100pct.wav").is_file()
    assert (ROOT / "_source" / "maple_alert.py").is_file()
    assert (ROOT / "_debug_tools" / "Calibrate Maple Alert.bat").is_file()


def test_repo_root_has_no_debug_batch_clutter() -> None:
    root_bats = sorted(path.name for path in ROOT.glob("*.bat"))
    assert root_bats == ["START_MAPLE_ALERT.bat"]


if __name__ == "__main__":
    test_repo_root_is_runnable_one_click_layout()
    test_repo_root_has_no_debug_batch_clutter()
    print("repository layout tests passed")
