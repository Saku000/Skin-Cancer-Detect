@echo off
title Skin Cancer Detect
call .venv\Scripts\activate.bat
start "Server" cmd /k "uvicorn main:app --host 0.0.0.0 --port 8000"
timeout /t 3 /nobreak >nul
start http://127.0.0.1:8000/ui
start http://127.0.0.1:8000/ui/mobile.html
