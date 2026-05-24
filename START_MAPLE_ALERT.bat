@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
title Maple Alert

set "SUPERVISOR=.\_internal\watchdog_supervisor.ps1"
if not exist "%SUPERVISOR%" set "SUPERVISOR=.\watchdog_supervisor.ps1"

if not exist "%SUPERVISOR%" (
  echo Could not find watchdog_supervisor.ps1.
  echo Make sure you extracted the whole MapleAlertPortable folder before running this.
  powershell -NoProfile -Command "for ($i=0; $i -lt 4; $i++) { [console]::beep(2200,180); Start-Sleep -Milliseconds 80 }"
  pause
  exit /b 1
)

echo Maple Alert is starting.
echo Keep this window open. Close it to stop monitoring.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%SUPERVISOR%"

echo.
echo Maple Alert stopped.
exit /b %ERRORLEVEL%
