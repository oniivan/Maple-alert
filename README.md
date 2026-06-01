# Maple Alert

Download the repo ZIP or clone the repo, extract it if needed, then run:

```text
START_MAPLE_ALERT.bat
```

Keep the black command window open while monitoring. Closing it stops the alert system and overlay.

## What It Does

- Lie detector visual alerts
- Minimap red-dot alerts with 20s persistence and 15s repeat while present
- Low-CPU screen polling
- Always-on-top status overlay
- Separate lie/player alert volumes up to 300%
- Watchdog crash/hang recovery
- Free Market safeguard prompt after a possible missed lie detection
- Setup check and redacted diagnostics bundle
- Optional Discord DM/webhook and Telegram alerts

This detects visual events and alerts the user.

## Files

- `START_MAPLE_ALERT.bat` - run this
- `config.toml` - settings
- `README_FIRST.txt` - short user notes
- `VERIFY.md` - source/package verification and release freshness checks
- `docs\COMMON_PROBLEMS.md` - troubleshooting
- `docs\AGENT_HANDOFF.md` - maintainer and AI-agent handoff notes
- `release_manifest.json` and `SHA256SUMS.txt` - package provenance
- `_debug_tools\` - optional calibration/test launchers
- `_source\` - source code, tests, and build script

## Support Tools

Open `_debug_tools\Setup Check.bat` to print folder, target-window, scaling,
system-volume, alert-volume, and remote-alert readiness.

Open `_debug_tools\Create Diagnostics.bat` to write a redacted text/JSON bundle
under `runtime\diagnostics\`. It does not include screenshots or debug crops.

Private settings can go in `config.local.toml` beside `config.toml`; it is
git-ignored and loaded after `config.toml`. Environment variables still win.
Run `MapleAlert.exe --config .\config.toml --validate-config` for a redacted
config check.

## Remote Alerts

Click `DM` on the overlay to paste Telegram or Discord details and send a test.
Discord DMs need a bot token plus numeric user ID. Telegram needs a bot token
plus chat ID, and the user must start the bot first.
