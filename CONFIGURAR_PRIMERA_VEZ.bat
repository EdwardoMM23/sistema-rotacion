@echo off
cd /d "%~dp0"
echo === Configuracion inicial del Sistema de Rotaciones ===
where py >nul 2>nul
if errorlevel 1 (
  echo No se encontro Python. Este script de instalacion requiere Python en el equipo servidor.
  echo Para operar sin Python instalado en el equipo servidor, consulta GUIA_UNIFICADA_PANTALLA_COMPARTIDA_Y_DESPLIEGUE.txt
  pause
  exit /b 1
)
py -3 -m venv .venv
if errorlevel 1 goto error
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto error
if not exist instance mkdir instance
if not exist .env.local (
  echo Crea una clave secreta privada y configura SECRET_KEY como variable de entorno de Windows antes de iniciar el servidor.
  echo No uses una clave publicada ni compartas la clave con usuarios.
)
echo Instalacion de dependencias terminada. Revisa la guia y configura SECRET_KEY antes de iniciar.
pause
exit /b 0
:error
echo Ocurrio un error. Copia el mensaje de la terminal para revisarlo.
pause
exit /b 1
