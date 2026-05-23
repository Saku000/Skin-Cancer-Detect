@echo off
title Skin Cancer Detect
echo ================================================
echo   Skin Cancer Detect — Starting...
echo ================================================
echo.

:: Check virtual environment
if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found.
    echo         Please run setup.bat first.
    pause
    exit /b 1
)

:: Check API key
if exist ".env" (
    findstr /C:"your_api_key_here" .env >nul 2>&1
    if not errorlevel 1 (
        echo [ERROR] Gemini API key not configured.
        echo         Open .env and replace "your_api_key_here" with your key.
        pause
        exit /b 1
    )
) else (
    echo [ERROR] .env file not found. Please run setup.bat first.
    pause
    exit /b 1
)

:: Activate environment
call .venv\Scripts\activate.bat

:: Start server in background
echo [....] Starting server on http://127.0.0.1:8000 ...
start /b "" .venv\Scripts\uvicorn.exe main:app --port 8000 > server.log 2>&1

:: Wait for server to be ready
echo [....] Waiting for server...
:wait_loop
timeout /t 1 /nobreak >nul
curl -s http://127.0.0.1:8000/health >nul 2>&1
if errorlevel 1 goto wait_loop

:: Open browser
echo [OK] Server is ready.
echo [....] Opening Web UI...
start http://127.0.0.1:8000/ui

echo.
echo ================================================
echo   Running at http://127.0.0.1:8000/ui
echo   Close this window to stop the server.
echo ================================================
echo.

:: Keep window open (server dies when this closes)
.venv\Scripts\uvicorn.exe main:app --port 8000
