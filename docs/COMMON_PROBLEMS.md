# Common Problems

## Maple Not Detected

Run `_debug_tools\Setup Check.bat` and look at the window candidates. If your client title does not include `Maple`, edit `capture.window_title` in `config.toml`.

If the alert tool starts before Maple, that is okay. It keeps checking and switches to the window when it appears.

## No Sound

Use the overlay `TEST` button. It plays the lie alert first, then the player alert.

Check these in order:

- Windows output is not muted.
- Windows output volume is at least `30%`.
- `LIE DETECT VOLUME` and `PLAYER DETECT VOLUME` are not near `0%`.
- The expected output device is selected in Windows.

## Low Volume Warning

The overlay pulses yellow when Windows output is muted or below `30%`. `IGNORE` appears only while the warning is active. After ignoring, a flashing yellow `WARN` button remains until the volume is fixed. A warning prompt appears if system volume stays muted or below `30%` for 3 minutes.

## Overlay Still Visible After Exit

Use the overlay `X` button when possible. It asks the whole one-click stack to quit.

If a leftover overlay remains after closing a console window, close it from Task Manager by ending `MapleAlert.exe`, then start again with `START_MAPLE_ALERT.bat`.

## Monitor Crashed Or Down

The watchdog restarts normal one-off crashes silently. It alerts only when the monitor is repeatedly crashing or unavailable long enough to matter.

Use `_debug_tools\Create Diagnostics.bat` to create a redacted support bundle under `runtime\diagnostics\`.

## Remote Alerts Not Sending

Click `DM` on the overlay and use the built-in test.

Telegram needs a bot token and chat ID. The recipient must start the bot first.

Discord DMs need a bot token and numeric user ID. Discord webhooks need a webhook URL.

Pushover needs an app token and user key. Pushover alerts use a one-shot emergency profile.

Private values should go in `config.local.toml` or the overlay settings, not in committed docs.

## Detector False Positives Or Misses

Use `_debug_tools\Test Image.bat` with a saved screenshot, or run:

```powershell
.\MapleAlert.exe --test-image C:\path\to\screenshot.png
```

The command saves ROI/debug crops under `debug_crops\` and prints detector details. Tune `roi.*` first if the target is not inside the crop. Tune `detection.*` only after the ROI is correct.

## CPU Too High

The default scan cadence is `0.25 FPS`, one scan every 4 seconds. Lower `capture.fps` in `config.toml` for less CPU, or raise it for faster response.

## Windows SmartScreen

The exe is unsigned. Windows may warn the first time it runs on a new PC. This does not mean the package is broken.
