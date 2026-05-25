#!/bin/bash
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 &
sleep 3
open http://127.0.0.1:8000/ui
open http://127.0.0.1:8000/ui/mobile.html
wait
