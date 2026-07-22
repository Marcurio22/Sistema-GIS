@echo off
setlocal EnableExtensions
REM Wrapper para el Programador de tareas (NDVI completo mensual, sin pause)
set "NO_PAUSE=1"
set "DIR=%~dp0"
if "%DIR:~-1%"=="\" set "DIR=%DIR:~0,-1%"
cd /d "%DIR%"
if not exist "ejecutar-ndvi-completo.bat" (
  echo Falta ejecutar-ndvi-completo.bat en %DIR%
  exit /b 1
)
call ejecutar-ndvi-completo.bat "%DIR%"
exit /b %ERRORLEVEL%
