@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1

if exist ".\MapleAlert.exe" (
  ".\MapleAlert.exe" --config ".\config.toml" --calibrate
) else if exist ".\.venv\Scripts\python.exe" (
  ".\.venv\Scripts\python.exe" ".\maple_alert.py" --config ".\config.toml" --calibrate
) else (
  echo Could not find MapleAlert.exe or .venv\Scripts\python.exe.
  echo Run the install steps in README.md, or use the packaged folder from dist.
)

echo.
echo Calibration stopped. Press any key to close this window.
pause >nul
