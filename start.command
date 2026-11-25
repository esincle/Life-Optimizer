#!/bin/bash
# Double-click this on macOS (Finder → Open). First time: right-click → Open.
cd "$(dirname "$0")"
chmod +x ./start.sh 2>/dev/null || true
./start.sh
