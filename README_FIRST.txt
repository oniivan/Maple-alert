Maple Alert portable
====================

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
player alert. Click/drag either meter to adjust that WAV volume up to 250%.
If the top bar flashes yellow for system volume, Windows is muted or below 70%.
The IGNORE button appears only while that warning is active. Click it to suppress
the current warning; a flashing WARN button remains while that warning is ignored.
If the top bar flashes red with MAPLESTORY NOT DETECTED, the game window was
not found and monitor fallback is active. Starting MapleStory later is okay; it
keeps checking and will switch when the window appears.
If the volume section turns red, the app's alert intensity is below 25%.

Do not run MapleAlert.exe directly unless you are troubleshooting. The BAT file
starts the crash/hang watchdog layers.

Optional:

  Edit config.toml to tune thresholds or add Telegram.
  Open README.md for the full technical notes.
