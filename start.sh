#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 was not found. Install it, then run this again."
  exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
  echo "Installing dependencies..."
  .venv/bin/python -m pip install -r requirements.txt
fi

echo "Starting Life Optimizer at http://127.0.0.1:5000/today/"
if command -v open >/dev/null 2>&1; then
  (sleep 1; open "http://127.0.0.1:5000/today/") &
elif command -v xdg-open >/dev/null 2>&1; then
  (sleep 1; xdg-open "http://127.0.0.1:5000/today/") &
fi

exec .venv/bin/python run.py
