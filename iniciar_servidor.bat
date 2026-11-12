@echo off
cd /d "%~dp0"
if "%SECRET_KEY%"=="" (
  echo ERROR: TI debe configurar SECRET_KEY como variable de entorno segura de Windows.
  echo No escribas ni publiques la clave en este archivo.
  pause
  exit /b 1
)
if not exist "venv\Scripts\python.exe" (
  echo ERROR: No existe el entorno venv. Consulta GUIA_DESPLIEGUE_PLANTA_PASO_A_PASO.txt
  pause
  exit /b 1
)
set HOST=0.0.0.0
set PORT=8080
venv\Scripts\python.exe run_server.py
pause
