@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3 from https://www.python.org/downloads/
  echo Make sure "Add python.exe to PATH" is checked.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  python -m venv .venv
  if errorlevel 1 (
    echo Failed to create .venv
    pause
    exit /b 1
  )
  echo Installing dependencies...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Failed to install requirements
    pause
    exit /b 1
  )
)

echo Starting Life Optimizer at http://127.0.0.1:5000/today/
start "" "http://127.0.0.1:5000/today/"
".venv\Scripts\python.exe" run.py
pause
