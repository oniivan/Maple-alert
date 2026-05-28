# Maple Alert

Download the repo ZIP or clone the repo, extract it if needed, then run:

```text
START_MAPLE_ALERT.bat
```

Keep the black command window open while monitoring. Closing it stops the alert system and overlay.

## What It Does

- Lie detector visual alerts
- Minimap red-dot alerts
- Low-CPU screen polling
- Always-on-top status overlay
- Adjustable alert volumes
- Watchdog crash/hang recovery
- Optional Discord DM/webhook and Telegram alerts

This detects visual events and alerts the user. It does not automate gameplay or solve CAPTCHA.

## Files

- `START_MAPLE_ALERT.bat` - run this
- `config.toml` - settings
- `README_FIRST.txt` - short user notes
- `_debug_tools\` - optional calibration/test launchers
- `_source\` - source code, tests, and build script

## Remote Alerts

Click `DM` on the overlay to paste Telegram or Discord details and send a test.
Discord DMs need a bot token plus numeric user ID. Telegram needs a bot token
plus chat ID, and the user must start the bot first.
