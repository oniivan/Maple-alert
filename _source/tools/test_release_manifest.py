from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def test_release_manifest_and_checksums_match_release_surface() -> None:
    manifest_path = ROOT / "release_manifest.json"
    sums_path = ROOT / "SHA256SUMS.txt"

    assert manifest_path.is_file(), "release_manifest.json"
    assert sums_path.is_file(), "SHA256SUMS.txt"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    files = {entry["path"]: entry for entry in manifest["files"]}
    required = [
        "START_MAPLE_ALERT.bat",
        "MapleAlert.exe",
        "config.toml",
        "templates/free_market_title.png",
        "_internal/watchdog_supervisor.ps1",
        "alert_sounds/captcha_100pct.wav",
        "alert_sounds/minimap_red_100pct.wav",
        "alert_sounds/watchdog_100pct.wav",
    ]

    for rel_path, entry in files.items():
        absolute = ROOT / rel_path
        assert absolute.is_file(), rel_path
        assert entry["bytes"] == absolute.stat().st_size
        assert entry["sha256"] == sha256_file(absolute)

    for rel_path in required:
        assert rel_path in files, rel_path

    sums_text = sums_path.read_text(encoding="utf-8")
    for rel_path in files:
        assert files[rel_path]["sha256"] in sums_text
        assert rel_path.replace("\\", "/") in sums_text


if __name__ == "__main__":
    test_release_manifest_and_checksums_match_release_surface()
    print("release manifest tests passed")
