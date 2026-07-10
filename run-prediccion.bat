@echo off
setlocal EnableExtensions
REM Wrapper para el Programador de tareas (sin pause, carpeta = donde esta el .bat)
set "NO_PAUSE=1"
set "DIR=%~dp0"
if "%DIR:~-1%"=="\" set "DIR=%DIR:~0,-1%"
cd /d "%DIR%"
if not exist "ejecutar-prediccion.bat" (
  echo Falta ejecutar-prediccion.bat en %DIR%
  exit /b 1
)
call ejecutar-prediccion.bat "%DIR%"
exit /b %ERRORLEVEL%
