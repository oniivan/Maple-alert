from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = [
    "maple" + "story",
    "maple" + "story " + "world" + "s",
    "world" + "s",
]
TEXT_SUFFIXES = {
    ".bat",
    ".md",
    ".ps1",
    ".py",
    ".toml",
    ".txt",
}


def tracked_files() -> list[Path]:
    git = Path(r"C:\Program Files\Git\cmd\git.exe")
    if not git.exists():
        return []
    output = subprocess.check_output(
        [str(git), "ls-files"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    )
    return [ROOT / line.strip() for line in output.splitlines() if line.strip()]


def test_public_wording_uses_maple_only() -> None:
    offenders: list[str] = []
    for path in tracked_files():
        if path.suffix.casefold() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").casefold()
        for forbidden in FORBIDDEN:
            if forbidden in text:
                offenders.append(f"{path.relative_to(ROOT)} contains {forbidden!r}")
    assert not offenders, "\n".join(offenders)


if __name__ == "__main__":
    test_public_wording_uses_maple_only()
    print("public wording tests passed")
