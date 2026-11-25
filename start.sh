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

LAN_IP=""
if command -v ipconfig >/dev/null 2>&1; then
  LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"
elif command -v hostname >/dev/null 2>&1; then
  LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
fi

echo "Starting Life Optimizer at http://127.0.0.1:5000/today/"
if [ -n "$LAN_IP" ]; then
  echo "iPhone (same Wi-Fi): http://${LAN_IP}:5000/today/"
  echo "Add to Home Screen steps: docs/iphone-pwa.md"
fi
if command -v open >/dev/null 2>&1; then
  (sleep 1; open "http://127.0.0.1:5000/today/") &
elif command -v xdg-open >/dev/null 2>&1; then
  (sleep 1; xdg-open "http://127.0.0.1:5000/today/") &
fi

exec .venv/bin/python run.py
