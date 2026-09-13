@echo off
title AssaFlex Bearing Design Tool
cd /d "%~dp0"

if not exist "runtime\python.exe" (
    echo.
    echo This app hasn't been set up yet on this computer.
    echo Run "build_portable_app.bat" once first ^(see README.md^), or if you
    echo were given a folder someone else already built, make sure a
    echo "runtime" folder came with it.
    echo.
    pause
    exit /b 1
)

echo Starting the AssaFlex Bearing Design Tool...
echo Your browser will open automatically in a few seconds.
echo.
echo To stop the app, close this window.
echo.
runtime\python.exe launcher.py
