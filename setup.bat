@echo off
title Setup
echo Creating virtual environment...
python -m venv .venv

echo Installing dependencies...
call .venv\Scripts\activate.bat
pip install -r requirements.txt

echo.
echo Done! Run start.bat to launch the app.
pause
