@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 (echo Python 3 が必要です & pause & exit /b 1)
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 (echo 依存ライブラリのインストールに失敗しました & pause & exit /b 1)
)
set DEMO_MODE=1
set NEXUS_SEED_DEMO=1
set NEXUS_DB_PATH=%CD%\data-demo.db
start "" cmd /c "timeout /t 3 /nobreak >nul & start http://127.0.0.1:8000"
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
