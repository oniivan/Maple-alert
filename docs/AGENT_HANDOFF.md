# Maple Alert Agent Handoff

Use this when an AI coding agent or maintainer continues Maple Alert work.

## Boundary

Maple Alert is a local visual alert monitor. It may capture screen pixels, inspect configured ROIs, play sounds, show an overlay, write logs/diagnostics, and send user-configured remote alerts.

Do not add gameplay automation, CAPTCHA solving, clicking, typing, memory reading, injection, hiding, evasion, or anti-detection behavior.

## Repo Surface

- Root folder is the one-click user package.
- `START_MAPLE_ALERT.bat` is the normal user entrypoint.
- `MapleAlert.exe`, `_internal\`, `alert_sounds\`, `config.toml`, `release_manifest.json`, and `SHA256SUMS.txt` are tracked release artifacts.
- `_source\maple_alert.py` is the CLI, overlay, watchdog, alert, and packaging entrypoint.
- `_source\vision_core.py` owns shared rectangle, scale, and crop helpers.
- `_source\detectors\minimap_red.py` owns minimap content isolation and red-dot shape detection.
- `_source\tools\run_fast_tests.py` is the default test runner.
- `config.local.toml`, `runtime\`, `logs\`, `debug_crops\`, and `docs\goals\` are local/ignored.

## Safe Default Commands

Run from the repo root:

```powershell
$files = @("_source\maple_alert.py", "_source\vision_core.py") +
  (Get-ChildItem _source\detectors -Filter *.py | ForEach-Object { $_.FullName }) +
  (Get-ChildItem _source\tools -Filter test_*.py | ForEach-Object { $_.FullName })
.\.venv\Scripts\python.exe -m py_compile @files
.\.venv\Scripts\python.exe _source\tools\run_fast_tests.py
.\.venv\Scripts\python.exe _source\maple_alert.py --help
.\MapleAlert.exe --help
.\MapleAlert.exe --build-info
```

Before changing detector thresholds, ROI math, color filtering, or scaling, run the optional private fixture tests when screenshots are available:

```powershell
.\.venv\Scripts\python.exe _source\tools\test_captcha_patch_images.py C:\path\to\screenshot-fixtures
.\.venv\Scripts\python.exe _source\tools\test_minimap_red_images.py C:\path\to\screenshot-fixtures
```

## Package Policy

Rebuild the one-click package after changes to source behavior, import paths, startup arguments, watchdog behavior, alert sounds, dependencies, or packaging inputs:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\_source\build_one_click.ps1
```

After rebuild:

- Run packaged `--help`, `--build-info`, and `--once` smokes.
- Run `_source\tools\test_release_manifest.py`.
- Confirm root `MapleAlert.exe` hash matches `_source\dist\MapleAlert\MapleAlert.exe`.
- Prefer a clean-source rebuild so `release_manifest.json` has `"source_dirty": false`.

## Config And Secrets

- Prefer `config.local.toml` or environment variables for private tokens/IDs.
- Do not print raw Telegram tokens, Discord tokens, chat IDs, user IDs, webhook URLs, or full diagnostic payloads.
- Use `--validate-config`, `--setup-check`, and `--diagnostics` for redacted support evidence.

## Completion Checklist

- Safety boundary is unchanged.
- Root user flow still starts with `START_MAPLE_ALERT.bat`.
- Fast tests pass without private screenshot fixtures.
- Source and packaged smoke commands pass when relevant.
- Package artifacts are refreshed when relevant.
- Docs match actual behavior.
