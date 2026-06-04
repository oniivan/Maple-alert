Maple Alert
===========

Run this:

  START_MAPLE_ALERT.bat

Keep the black command window open while monitoring. Closing it or pressing
Ctrl+C stops the alert system and overlay.

A small "LIVE" overlay should appear. Drag it with the mouse if it covers
something. The moving spinner means the overlay itself is alive. LIE and PLAYER
only appear after detection, then show how many minutes ago each signal was last
seen. Click the small - at the top-right to collapse the drawer to the main
status bar; it changes to v while collapsed. Click the small X at the top-right
of the overlay to quit the whole alert stack.

The overlay has a TEST button plus separate LIE DETECT VOLUME and PLAYER
DETECT VOLUME filled meters. Click TEST to play the lie alert first, then the
player alert. Click/drag either meter to adjust that WAV volume up to 300%.
Click DM on the top bar to add Telegram, Discord, or Pushover remote alert details and
send a test message.
If the top bar flashes yellow for system volume, Windows is muted or below 30%.
The IGNORE button appears only while that warning is active. Click it to suppress
the current warning; a flashing WARN button remains while that warning is ignored.
A warning prompt appears if system volume stays muted or below 30% for 3 minutes,
and configured DMs are sent at the same time.
If the top bar flashes red with MAPLE NOT DETECTED, the game window was
not found and monitor fallback is active. Starting Maple later is okay; it
keeps checking and will switch when the window appears.
If the top bar flashes red with MONITOR CRASHED or MONITOR DOWN, the monitor
has been crashing repeatedly or has been unavailable long enough to matter.
If the volume section turns red, the app's alert intensity is below 25%.
Player alerts start after the configured persistence delay, then repeat about
every 15 seconds while the marker remains present.

Use `START_MAPLE_ALERT.bat` for normal monitoring. Running `MapleAlert.exe`
directly is mainly for troubleshooting because the BAT file starts the
crash/hang watchdog layers.

Optional:

  Edit config.toml to tune thresholds or add Telegram/Discord/Pushover.
  Put private tokens/IDs in config.local.toml instead of config.toml.
  Open _debug_tools\Setup Check.bat if you are unsure the right window/audio/settings are ready.
  Open _debug_tools\Create Diagnostics.bat to make a redacted support bundle.
  Open README.md for a short feature list.
  Open docs\COMMON_PROBLEMS.md for troubleshooting.
  Open VERIFY.md for source/package smoke checks and release freshness notes.
  Open release_manifest.json or SHA256SUMS.txt to verify package hashes.
