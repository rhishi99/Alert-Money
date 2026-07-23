@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stockpulse.ps1" restart both
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stockpulse.ps1" status
