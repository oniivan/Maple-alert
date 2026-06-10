from __future__ import annotations

import subprocess
import sys
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parent

OPTIONAL_FIXTURE_TESTS = {
    "test_captcha_patch_images.py",
    "test_dead_player_images.py",
    "test_free_market_title_images.py",
    "test_minimap_red_images.py",
}


def discover_fast_tests() -> list[Path]:
    return [
        path
        for path in sorted(TOOLS_DIR.glob("test_*.py"))
        if path.name not in OPTIONAL_FIXTURE_TESTS
    ]


def main() -> int:
    tests = discover_fast_tests()
    if not tests:
        print("No fast tests found.")
        return 1

    failures: list[Path] = []
    for test_path in tests:
        print(f"RUN {test_path.name}", flush=True)
        completed = subprocess.run([sys.executable, str(test_path)], check=False)
        if completed.returncode != 0:
            failures.append(test_path)
            print(f"FAIL {test_path.name}: exit {completed.returncode}", flush=True)

    print(
        f"fast tests complete: files={len(tests)} failures={len(failures)} "
        f"optional_fixture_tests={len(OPTIONAL_FIXTURE_TESTS)}",
        flush=True,
    )
    if failures:
        print("failed tests:")
        for path in failures:
            print(f"  {path.name}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
