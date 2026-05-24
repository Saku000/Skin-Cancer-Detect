#!/bin/bash
source .venv/bin/activate
uvicorn main:app --port 8000 &
sleep 3
open http://127.0.0.1:8000/ui
wait
