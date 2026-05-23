@echo off
title Skin Cancer Detect — Setup
echo ================================================
echo   Skin Cancer Detect — First-time Setup
echo ================================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+ and try again.
    pause
    exit /b 1
)
echo [OK] Python found.

:: Create virtual environment
if exist ".venv" (
    echo [SKIP] Virtual environment already exists.
) else (
    echo [....] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created.
)

:: Activate and install dependencies
echo [....] Installing dependencies...
call .venv\Scripts\activate.bat
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

:: Check .env
if not exist ".env" (
    echo.
    echo [WARN] .env file not found. Creating template...
    echo GEMINI_API_KEY=your_api_key_here > .env
)

:: Check API key
findstr /C:"your_api_key_here" .env >nul 2>&1
if not errorlevel 1 (
    echo.
    echo ================================================
    echo   ACTION REQUIRED
    echo   Open .env and replace "your_api_key_here"
    echo   with your actual Gemini API key.
    echo   Get one at: aistudio.google.com
    echo ================================================
)

echo.
echo ================================================
echo   Setup complete! Run start.bat to launch.
echo ================================================
echo.
pause
