@echo off
setlocal

cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python is not installed or not in PATH.
  echo Install Python 3.11+ and try again.
  pause
  exit /b 1
)

python -m pip install -e . >nul
if errorlevel 1 (
  echo [ERROR] Failed to install dependencies.
  pause
  exit /b 1
)

start "" http://127.0.0.1:8000
python -m uvicorn tax_exam_app.web:app --app-dir src --host 127.0.0.1 --port 8000

endlocal
