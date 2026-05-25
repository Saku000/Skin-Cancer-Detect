#!/bin/bash
PYTHON=".venv/bin/python3"

if [ -f "$PYTHON" ]; then
    echo "Virtual environment found. Verifying..."
    if ! $PYTHON -c "print('ok')" &>/dev/null; then
        echo "Environment is broken. Recreating..."
        rm -rf .venv
        python3 -m venv .venv
    else
        echo "Environment OK."
    fi
else
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

echo "Checking packages..."
.venv/bin/python3 -m pip install -r requirements.txt --quiet

echo ""
echo "Done! Run ./start.sh to launch the app."
