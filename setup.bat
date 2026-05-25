@echo off
title Setup
set PYTHON=.venv\Scripts\python.exe

if exist %PYTHON% (
    echo Virtual environment found. Verifying...
    %PYTHON% -c "print('ok')" >nul 2>&1
    if errorlevel 1 (
        echo Environment is broken. Recreating...
        rmdir /s /q .venv
        goto :create
    )
    echo Checking packages...
    %PYTHON% -m pip install -r requirements.txt --quiet
    goto :done
)

:create
echo Creating virtual environment...
python -m venv .venv
if errorlevel 1 (
    echo Failed. Make sure Python is installed and added to PATH.
    pause
    exit /b 1
)
echo Installing dependencies...
%PYTHON% -m pip install -r requirements.txt

:done
echo.
echo Done! Run start.bat to launch the app.
pause
