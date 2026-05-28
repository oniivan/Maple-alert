@echo off
setlocal
cd /d "%~dp0.."
set PYTHONUTF8=1

if exist ".\MapleAlert.exe" (
  ".\MapleAlert.exe" --config ".\config.toml" --diagnostics
) else if exist ".\.venv\Scripts\python.exe" (
  ".\.venv\Scripts\python.exe" ".\_source\maple_alert.py" --config ".\config.toml" --diagnostics
) else (
  echo Could not find MapleAlert.exe or .venv\Scripts\python.exe.
  echo Run START_MAPLE_ALERT.bat from the repo root first, or rebuild from _source.
)

echo.
echo Diagnostics finished. Press any key to close this window.
pause >nul
