@echo off
REM Sweep strays + start bot + webhook. Double-clickable.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stockpulse.ps1" start both
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stockpulse.ps1" status
