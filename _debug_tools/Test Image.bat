@echo off
setlocal
cd /d "%~dp0.."
set PYTHONUTF8=1

set /p IMAGE_PATH=Drag/paste a screenshot path here, then press Enter: 
set IMAGE_PATH=%IMAGE_PATH:"=%

if exist ".\MapleAlert.exe" (
  ".\MapleAlert.exe" --config ".\config.toml" --test-image "%IMAGE_PATH%"
) else if exist ".\.venv\Scripts\python.exe" (
  ".\.venv\Scripts\python.exe" ".\_source\maple_alert.py" --config ".\config.toml" --test-image "%IMAGE_PATH%"
) else (
  echo Could not find MapleAlert.exe or .venv\Scripts\python.exe.
  echo Run START_MAPLE_ALERT.bat from the repo root first, or rebuild from _source.
)

echo.
echo Test finished. Press any key to close this window.
pause >nul
