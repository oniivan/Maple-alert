from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from maple_alert import APP_NAME, APP_VERSION, build_info_payload  # noqa: E402


def test_build_info_payload_reads_release_manifest() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        manifest_path = Path(temp_dir) / "release_manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "app_name": APP_NAME,
                    "app_version": APP_VERSION,
                    "built_at_utc": "2026-05-28T00:00:00Z",
                    "source_commit": "abc123",
                    "source_dirty": False,
                    "files": [{"path": "MapleAlert.exe", "sha256": "deadbeef", "bytes": 123}],
                }
            ),
            encoding="utf-8",
        )

        payload = build_info_payload(Path(temp_dir))

        assert payload["app_name"] == APP_NAME
        assert payload["app_version"] == APP_VERSION
        assert payload["release_manifest"]["source_commit"] == "abc123"
        assert payload["release_manifest"]["files"][0]["path"] == "MapleAlert.exe"


if __name__ == "__main__":
    test_build_info_payload_reads_release_manifest()
    print("build info tests passed")
