# Maple Visual Alert Monitor

This is a local Windows visual monitor. It reads screen pixels, checks two configurable regions of interest, and alerts when it sees either a centered CAPTCHA-like dialog or a red dot in the top-left minimap.

This implementation uses ordinary Windows screen capture and optional window-title lookup.

## What It Needs

- Windows with Python 3.10 or newer.
- Python packages in `requirements.txt`.
- Permission to capture the screen and play local audio.
- Optional Telegram bot token and chat ID, either in `config.toml` or environment variables:
  - `TELEGRAM_BOT_TOKEN`
  - `TELEGRAM_CHAT_ID`
- Optional cropped CAPTCHA template image if you want template matching. The heuristic detector works without it, but a template can improve reliability.

## Architecture

- Source layout:
  - `maple_alert.py` is still the CLI, overlay, watchdog, alert, and packaging entrypoint.
  - `vision_core.py` holds shared rectangle, scale, and crop helpers used by live capture and detector tests.
  - `detectors/minimap_red.py` holds the minimap content isolation and red-dot shape detector.
- `mss` captures only small ROIs. The default visual scan cadence is `0.25 FPS`, meaning one scan every 4 seconds, to keep CPU low.
- `pygetwindow` tries to locate a visible window whose title contains `Maple`.
- If the window is not found, capture falls back to the configured monitor.
- ROIs are proportional, so they scale with resolution/window size:
  - CAPTCHA: center 50% by default.
  - Minimap: top-left 30% x 31% by default, then the detector isolates the actual minimap content inside that search area.
- Fixed-pixel detector sizes are also scaled automatically. The reference screenshots are `1919x1079`; live/window captures are compared to that reference and the script applies a `pixel_scale` to the CAPTCHA patch, minimap frame search, and red-dot size thresholds.
- CAPTCHA detection uses optional multi-scale template matching plus a strict visual heuristic. The heuristic scans the center ROI for a `145x100` blue lie-detector panel patch with a dark detector-icon patch in its upper-right area, then checks the blue pixels for tight color and texture ranges.
- Minimap detection isolates the minimap content area, thresholds strict bright-red HSV pixels, then accepts only small circular dot-shaped blobs.
- Alert timing is stateful:
  - CAPTCHA: alerts immediately when visible, then repeats every 30 seconds while still visible.
  - Minimap red: waits until red has been continuously visible for 20 seconds, alerts once, then repeats every 15 seconds while still visible. If red disappears, the 20-second timer resets.
- The sound is generated as WAV audio using the same alert frequencies/durations that the old `winsound.Beep()` version used. The overlay has separate `LIE DETECT VOLUME` and `PLAYER DETECT VOLUME` meters; each controls the real WAV amplitude for that alert type. Meters range from `0%` to `300%`; Windows master volume still applies.
- The overlay also checks Windows master output volume. If the system is muted or below `30%`, the heartbeat bar pulses yellow and says so. `IGNORE` appears only while that warning is active; after ignoring, a flashing yellow `WARN` button remains while the low-volume condition still exists. A warning prompt appears if the low-volume condition lasts 3 minutes, and configured DMs are sent at the same time.
- If the Maple window is not found while `target_window = true`, the overlay flashes red with `MAPLE NOT DETECTED`. The monitor keeps checking, so starting Maple after the alert tool is already running will switch capture to the window once the title appears.
- Remote alerts stay off by default until you enable Telegram, Discord, or Pushover.

## Install

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
Copy-Item config.example.toml config.toml
```

## Run

Safe local mode:

```powershell
python .\maple_alert.py --config .\config.toml
```

List visible windows to confirm the title substring:

```powershell
python .\maple_alert.py --list-windows
```

Print a player-facing setup readiness report:

```powershell
python .\maple_alert.py --config .\config.toml --setup-check
```

Validate config values without printing credentials:

```powershell
python .\maple_alert.py --config .\config.toml --validate-config
```

Print package build metadata:

```powershell
python .\maple_alert.py --config .\config.toml --build-info
```

Write a redacted support diagnostics bundle:

```powershell
python .\maple_alert.py --config .\config.toml --diagnostics
```

Diagnostics are written under `runtime\diagnostics\` by default and include
text/JSON summaries only. Remote alert tokens, IDs, and webhooks are redacted,
and screenshots/debug crops are not included.

For private machine-specific values, create `config.local.toml` beside
`config.toml`. It is git-ignored, loaded after `config.toml`, and still loses
to environment variables. Use it for tokens, chat IDs, webhooks, and personal
volume/timing overrides.

Capture one sample and save cropped ROIs to `debug_crops`:

```powershell
python .\maple_alert.py --once
```

Live calibration view:

```powershell
python .\maple_alert.py --calibrate
```

Press `q` or `Esc` to close the calibration windows.

Watchdog mode:

```powershell
python .\maple_alert.py --config .\config.toml --watchdog
```

Watchdog mode starts the monitor as a child process. The monitor writes `runtime\heartbeat.json` every few seconds. The watchdog restarts the monitor if the child exits or the heartbeat goes stale, but it only plays the distinct warning tone after sustained downtime or repeated failures. The one-click batch file adds an outer PowerShell supervisor that watches `runtime\watchdog_heartbeat.json`; if the watchdog exits or hangs while the command window is open, the outer supervisor plays its own chirp and restarts the watchdog.

## One-Click Repo Folder

The repo folder is meant to be simple to send to someone else. After downloading or copying the repo folder, run only this file:

```text
START_MAPLE_ALERT.bat
```

That one BAT starts the outer supervisor, watchdog, monitor, and heartbeat overlay. Keep the black command window open while monitoring. Closing it or pressing `Ctrl+C` stops the alert system and the overlay.

The overlay looks like this:

```text
LIVE |
SYSTEM VOL OK 100%
[TEST] LIE DETECT VOLUME 200% | PLAYER DETECT VOLUME 200%
```

The spinner changes every few tenths of a second so you can see the overlay itself is alive. `LIE` and `PLAYER` are hidden until seen; after a detection, the top line uses `LIVE | LIE 2m ago PLAYER 1m ago`. During an active lie/player alert, the top bar flashes red with the current alert. Drag the overlay with the mouse if it covers something. Click the small `-` in the top-right to collapse the drawer to only the main status bar; it changes to `v` when collapsed. Click the small `X` in the top-right of the overlay to quit the whole one-click alert stack. Click `TEST` to play the lie detector alert first, then the player detected alert; each meter lights while its sound is being tested. Click or drag either filled meter to change that alert's intensity; settings are saved to `runtime\alert_settings.json`.

If the system volume line flashes yellow, Windows audio is muted or below `30%`. The `IGNORE` button appears only while that warning is active; click it to suppress the current warning. While ignored, the small `WARN` button stays visible and flashes yellow until system volume recovers or you click it to re-enable the warning. If the condition lasts 3 minutes, a warning prompt appears and configured DMs are sent. If an alert volume section turns red, that alert intensity is below `25%`.

If the capture size changes while running, the monitor recalculates `pixel_scale` and the overlay briefly shows `DETECTED NEW RESOLUTION WxH`. The command window also prints useful state changes such as Maple detected/not detected, detected resolution changes, detection alerts, repeated continued alerts, and cleared detections.

The repo folder also includes:

- `MapleAlert.exe` - the packaged Python app. Use `START_MAPLE_ALERT.bat` for normal monitoring; direct exe runs are mainly for troubleshooting.
- `config.toml` - editable settings.
- `alert_sounds\` - exported WAV copies of the generated alert tones.
- `README_FIRST.txt` - short instructions for the recipient.
- `README.md` - full technical notes.
- `_internal\` - packaged dependencies and the hidden supervisor script.

Optional support launchers live in `_debug_tools\`:

- `Setup Check.bat` - prints a readiness report for folder files, target window, scaling, audio, alert volumes, and remote alerts.
- `Create Diagnostics.bat` - creates a redacted text/JSON bundle under `runtime\diagnostics\` without screenshots.

Build or rebuild the one-click files from this source folder:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_one_click.ps1
```

The build refreshes the repo root files:

```text
MapleAlert.exe
_internal\
alert_sounds\
config.toml
release_manifest.json
SHA256SUMS.txt
```

To move it to another Windows PC, copy or download the repo folder, then double-click `START_MAPLE_ALERT.bat`. If the new PC has a different resolution, scaling, or game window size, edit `config.toml` and use the commands in the calibration section below.

The exe is unsigned, so Windows may show a SmartScreen warning the first time it runs.

## Verification

From the repo root, run the default local verification baseline:

```powershell
$files = @("_source\maple_alert.py", "_source\vision_core.py") +
  (Get-ChildItem _source\detectors -Filter *.py | ForEach-Object { $_.FullName }) +
  (Get-ChildItem _source\tools -Filter test_*.py | ForEach-Object { $_.FullName })
.\.venv\Scripts\python.exe -m py_compile @files
.\.venv\Scripts\python.exe _source\tools\run_fast_tests.py
.\.venv\Scripts\python.exe _source\maple_alert.py --help
.\MapleAlert.exe --help
```

The fast runner executes all script-style tests except private screenshot
fixture checks. The detector fixture checks are explicit optional commands:

```powershell
.\.venv\Scripts\python.exe _source\tools\test_captcha_patch_images.py C:\path\to\screenshot-fixtures
.\.venv\Scripts\python.exe _source\tools\test_minimap_red_images.py C:\path\to\screenshot-fixtures
```

Run the optional fixture checks before detector, ROI, scaling, or threshold
changes when the private screenshot fixtures are available. See `VERIFY.md` for
the release artifact freshness policy and `docs\AGENT_HANDOFF.md` for safe
continuation notes.

## Watchdog Limits

The watchdog is practical protection, not a guarantee. It can catch normal Python crashes, module errors, most hangs that stop the capture loop, and stale heartbeat writes. A single monitor crash is logged and restarted quietly. The watchdog alarm starts only if the monitor is unavailable for 120 seconds or if 3 monitor failures happen inside 5 minutes; it repeats no faster than every 120 seconds while the monitor remains unhealthy. The overlay flashes red with `MONITOR CRASHED X TIMES IN 5 MINS` or `MONITOR DOWN Xm+`, then keeps that warning latched until the monitor has recovered cleanly for 600 seconds. The batch launcher also starts an outer PowerShell supervisor, which restarts the watchdog if the watchdog exits or stops updating its own heartbeat for about 30 seconds while the launcher window is still open.

No local wrapper can be completely failsafe if Windows sleeps, the PC loses power, audio is muted, the command window is closed, the whole system freezes, PowerShell itself hangs, or Telegram/network access is unavailable. For extra resilience, keep the command window visible and use Windows Task Scheduler to start `START_MAPLE_ALERT.bat` at login.

Sound patterns:

```text
CAPTCHA / lie detector: 1300 Hz for 450 ms, then 1600 Hz for 450 ms, generated as WAV.
Red minimap marker:     900 Hz for 250 ms, then 900 Hz for 250 ms, generated as WAV.
Python watchdog alert:  1800 Hz for 250 ms, then 900 Hz for 250 ms, repeated 3 times, generated as WAV.
Outer supervisor alert: 2200 Hz for 180 ms, repeated 4 times with short gaps.
```

## Screenshot Test

To test a saved full-screen screenshot directly, use:

```powershell
.\MapleAlert.exe --config .\config.toml --test-image "C:\path\to\screenshot.png"
```

In the repo folder, open PowerShell or Command Prompt there and run the same command with `MapleAlert.exe`. This runs the same ROI and detector logic without live screen capture, saves the CAPTCHA/minimap crops to `debug_crops`, and prints the confidence details. If this fails while the CAPTCHA is visible in the saved `*_captcha_roi.png`, tune `[detection.captcha]`; if the CAPTCHA is not visible in that crop, tune `[roi.captcha]`.

In live monitoring, the detector saves a crop around the best CAPTCHA patch candidate only when the CAPTCHA alert actually fires. Test-image runs also save a crop for inspection. The rolling folder is `debug_crops\blue_blocks`; it keeps only ten files, `blue_block_00_*.png` through `blue_block_09_*.png`, and overwrites the oldest slot as it continues.

## Telegram

Set these in PowerShell:

```powershell
$env:TELEGRAM_BOT_TOKEN = "123456:your_token"
$env:TELEGRAM_CHAT_ID = "123456789"
```

Then edit `config.toml`:

```toml
[alerts]
safe_mode = false
telegram_enabled = true
```

## Tuning

Alert timing and sound:

```toml
[alerts]
sound_multiplier = 2
alert_volume_percent = 200
lie_detect_volume_percent = 200
player_detected_volume_percent = 200
alert_settings_file = "runtime/alert_settings.json"
captcha_repeat_seconds = 30
minimap_required_seconds = 20
minimap_repeat_seconds = 30
status_interval_seconds = 15
```

`sound_multiplier` and `alert_volume_percent` are kept as fallbacks for older configs. New configs use `lie_detect_volume_percent` and `player_detected_volume_percent`; `100` is normal generated-WAV amplitude and `250` is the highest generated-WAV amplitude.

Watchdog health thresholds:

```toml
[watchdog]
crash_window_seconds = 300
crash_alert_count = 3
monitor_down_alert_seconds = 120
watchdog_realert_seconds = 120
healthy_clear_seconds = 600
```

To export or regenerate the WAV files:

```powershell
.\MapleAlert.exe --config .\config.toml --export-alert-wavs alert_sounds
```

Heartbeat overlay:

```toml
[overlay]
enabled = true
x = 320
y = 48
opacity = 0.86
update_interval_ms = 250
warning_seconds = 6
stale_seconds = 14
font_size = 10
```

When the console says `Maple not detected` or `Capture source=monitor`, the script did not find the configured window title and is watching the selected monitor instead. In monitor fallback, auto-scaling is based on the full monitor capture size. If Maple is a smaller non-maximized window inside that monitor, the scale can be wrong because the script does not yet visually infer the game window bounds from the monitor image. Run `MapleAlert.exe --list-windows` from the repo folder, find the exact Maple title, and update `window_title` in `config.toml` if needed. The default title substring is `Maple`, which should match common Maple client titles.

Resolution scaling:

```toml
[scaling]
enabled = true
reference_width = 1919
reference_height = 1079
min_scale = 0.50
max_scale = 1.60
```

Whenever the capture source or capture size changes, the console and log print the detected resolution and scale, for example `Detected new resolution 2560x1440; scale_x=1.3340 scale_y=1.3346 pixel_scale=1.3343`. A 1280x720 capture uses about `0.667x`; a 2560x1440 capture uses about `1.334x`.

Red minimap detection is now a tight dot-shape detector. It first isolates the minimap content area, then looks for bright circular red dot components that are `8-13 px` at the reference resolution and auto-scaled at other resolutions:

```toml
[detection.minimap]
enabled = true
red_hue_max = 8
red_hue_wrap_min = 174
saturation_min = 220
value_min = 120
dot_width_min = 8
dot_width_max = 13
dot_height_min = 8
dot_height_max = 13
dot_area_min = 42.0
dot_area_max = 85.0
dot_circularity_min = 0.85
dot_extent_min = 0.53
dot_pixel_count_min = 50
dot_mean_saturation_min = 240
dot_mean_value_min = 220
```

To disable red minimap detection completely, set:

```toml
[detection.minimap]
enabled = false
```

CAPTCHA detection is intentionally strict. It looks for the lie-detector panel patch, not just a generic blue block:

```toml
[detection.captcha]
confidence_threshold = 0.90
patch_width = 145
patch_height = 100
patch_scale_min = 0.94
patch_scale_max = 1.06
patch_blue_fill_min = 0.82
patch_lower_blue_fill_min = 0.94
patch_dark_fill_min = 0.33
patch_dark_fill_max = 0.52
patch_blue_h_mean_min = 104.0
patch_blue_h_mean_max = 106.5
patch_blue_s_mean_min = 148.0
patch_blue_s_mean_max = 162.0
patch_blue_v_mean_min = 178.0
patch_blue_v_mean_max = 194.0
patch_blue_h_std_max = 2.5
patch_blue_s_std_max = 12.0
patch_blue_v_std_max = 16.0
```

If CAPTCHA alerts are too sensitive, raise `patch_blue_fill_min`, raise `patch_lower_blue_fill_min`, narrow the blue mean ranges, or tighten `patch_dark_fill_min`/`patch_dark_fill_max`.

If CAPTCHA alerts are missed, widen `patch_scale_min`/`patch_scale_max` slightly, loosen the blue mean/std ranges, or provide a cropped template image and set:

```toml
[detection.captcha]
patch_scale_min = 0.90
patch_scale_max = 1.10
patch_blue_fill_min = 0.78
patch_lower_blue_fill_min = 0.90
patch_dark_fill_min = 0.25
patch_dark_fill_max = 0.60
template_path = "templates/captcha_dialog.png"
template_threshold = 0.82
```

The script logs detections and debug details to `logs/detections.log`.

Rolling CAPTCHA/red-dot crops:

```toml
[debug]
save_blue_block_crops = true
blue_block_crop_dir = "debug_crops/blue_blocks"
blue_block_crop_size = 180
blue_block_crop_limit = 10
save_red_dot_crops = true
red_dot_crop_dir = "debug_crops/red_dots"
red_dot_crop_size = 100
red_dot_crop_limit = 10
```

Red-dot crops are separate from CAPTCHA patch crops and are saved only when a minimap-red alert fires after the configured persistence delay.
