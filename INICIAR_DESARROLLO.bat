@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Primero ejecuta CONFIGURAR_PRIMERA_VEZ.bat
  pause
  exit /b 1
)
if "%SECRET_KEY%"=="" (
  echo Falta SECRET_KEY. Configurala en las variables de entorno de Windows antes de iniciar.
  pause
  exit /b 1
)
.venv\Scripts\python.exe run_server.py
pause
