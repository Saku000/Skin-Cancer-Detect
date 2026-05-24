#!/bin/bash
echo "Creating virtual environment..."
python3 -m venv .venv

echo "Installing dependencies..."
source .venv/bin/activate
pip install -r requirements.txt

echo ""
echo "Done! Run ./start.sh to launch the app."
