@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "build_portable_app.ps1"
pause
