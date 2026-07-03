@echo off
REM Pack diario: ndvi_diax + generate_thumbnails
REM Uso: ejecutar-ndvi-diario.bat [C:\GIS\comunidades\mi_comunidad]
setlocal
set "DIR=%~1"
if "%DIR%"=="" set "DIR=%~dp0"
if not exist "%DIR%\server.py" (
  echo No es una instancia GIS: %DIR%
  exit /b 1
)
set "PY=C:\Users\UBU\anaconda3\envs\gis\python.exe"
if not exist "%PY%" set "PY=python"
cd /d "%DIR%"
"%PY%" -u src\scripts\pack_ndvi_diario.py
exit /b %ERRORLEVEL%
