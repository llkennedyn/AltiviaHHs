@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Preparando entorno Python...
  py -3 -m venv .venv
  if errorlevel 1 (echo Instala Python 3.10+ desde python.org y activa PATH & pause & exit /b 1)
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (echo Error instalando dependencias & pause & exit /b 1)
start "" http://127.0.0.1:8765
".venv\Scripts\python.exe" app.py
pause
