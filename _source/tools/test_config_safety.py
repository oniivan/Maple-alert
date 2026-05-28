from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from maple_alert import (  # noqa: E402
    SystemVolumeState,
    build_redacted_config,
    build_setup_check_report,
    load_config,
    validate_config,
)


def test_config_local_overrides_base_config_and_is_redacted() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        config_path = Path(temp_dir) / "config.toml"
        config_path.write_text(
            """
[capture]
window_title = "Maple"

[alerts]
lie_detect_volume_percent = 100

[telegram]
bot_token = ""
chat_id = ""
""",
            encoding="utf-8",
        )
        (Path(temp_dir) / "config.local.toml").write_text(
            """
[alerts]
lie_detect_volume_percent = 175

[telegram]
bot_token = "private-token"
chat_id = "private-chat-id"
""",
            encoding="utf-8",
        )

        config = load_config(config_path)
        redacted = json.dumps(build_redacted_config(config), sort_keys=True)

        assert config["alerts"]["lie_detect_volume_percent"] == 175
        assert config["telegram"]["bot_token"] == "private-token"
        assert str(config_path.resolve()) in config["_loaded_config_files"]
        assert str((Path(temp_dir) / "config.local.toml").resolve()) in config["_loaded_config_files"]
        assert "private-token" not in redacted
        assert "private-chat-id" not in redacted


def test_validate_config_reports_missing_remote_pair_without_secrets() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        config_path = Path(temp_dir) / "config.toml"
        config_path.write_text(
            """
[notifications]
remote_enabled = true

[telegram]
bot_token = "private-token"
chat_id = ""
""",
            encoding="utf-8",
        )

        config = load_config(config_path)
        issues = validate_config(config)
        issue_text = json.dumps(issues, sort_keys=True)

        assert any(issue["code"] == "telegram_incomplete" for issue in issues)
        assert "private-token" not in issue_text


def test_setup_check_includes_config_validation_summary() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        config_path = Path(temp_dir) / "config.toml"
        config_path.write_text(
            """
[capture]
target_window = true
window_title = ""
""",
            encoding="utf-8",
        )

        config = load_config(config_path)
        report = build_setup_check_report(config, config_path, windows=[], system_volume_state=SystemVolumeState(80, False))

        assert "Config Validation: 1 error, 0 warnings" in report
        assert "capture.window_title" in report


if __name__ == "__main__":
    test_config_local_overrides_base_config_and_is_redacted()
    test_validate_config_reports_missing_remote_pair_without_secrets()
    test_setup_check_includes_config_validation_summary()
    print("config safety tests passed")
