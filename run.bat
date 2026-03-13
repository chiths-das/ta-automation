@echo off
setlocal
:: ═══════════════════════════════════════════════════════
::  TA Automation — Windows Launcher
::  Double-click this file (or put a shortcut on desktop)
:: ═══════════════════════════════════════════════════════

cd /d "%~dp0"

:: ── First-run: create config from template ────────────────────────────────
if not exist "config.local.yaml" (
    echo.
    echo  ┌─────────────────────────────────────────┐
    echo  │  First-time setup                       │
    echo  │                                         │
    echo  │  1. config.local.yaml has been created  │
    echo  │  2. Fill in your API keys               │
    echo  │  3. Double-click run.bat again           │
    echo  └─────────────────────────────────────────┘
    echo.
    copy config.yaml config.local.yaml >nul
    echo  Opening config.local.yaml in Notepad...
    start notepad config.local.yaml
    pause
    exit /b 0
)

:: ── Launch ────────────────────────────────────────────────────────────────
echo.
echo  Starting TA Automation...
echo  The browser will open automatically at http://localhost:8501
echo  Close this window to stop the app.
echo.

start "" http://localhost:8501
ta_automation.exe

pause
