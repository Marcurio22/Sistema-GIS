@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM Genera mapa ETP continuo (ImageMosaic global) desde esta plantilla.
REM Uso: ejecutar-mapas-etp-continuos.bat
REM      ejecutar-mapas-etp-continuos.bat 2026-07-19

set "BASE=%~dp0"
if "!BASE:~-1!"=="\" set "BASE=!BASE:~0,-1!"

set "FECHA_ARG=%~1"
set "SCRIPT=%BASE%\src\scriptqgis.py"
if not exist "%SCRIPT%" (
  echo [ERROR] No existe: %SCRIPT%
  pause
  exit /b 1
)

set "METEO_ENV_FILE=%BASE%\.env"
set "PYTHONPATH=%BASE%\src"

set "ENV_ROOT=C:\Users\UBU\anaconda3\envs\gis"
set "PY=%ENV_ROOT%\python.exe"
if not exist "%PY%" set "PY=python"

if exist "%ENV_ROOT%\python.exe" (
  set "PATH=%ENV_ROOT%;%ENV_ROOT%\Library\mingw-w64\bin;%ENV_ROOT%\Library\usr\bin;%ENV_ROOT%\Library\bin;%ENV_ROOT%\Scripts;%ENV_ROOT%\bin;%PATH%"
)
if exist "%ENV_ROOT%\Library\share\proj" set "PROJ_LIB=%ENV_ROOT%\Library\share\proj"
if exist "%ENV_ROOT%\Library\share\gdal" set "GDAL_DATA=%ENV_ROOT%\Library\share\gdal"
set "PYTHONUNBUFFERED=1"
set "PYTHONUTF8=1"

if not exist "%BASE%\logs" mkdir "%BASE%\logs"
for /f "tokens=1-4 delims=/-. " %%a in ("%date%") do set "STAMP=%%d-%%b-%%c"
set "LOG=%BASE%\logs\mapas-etp-continuos-%STAMP%.log"

cd /d "%BASE%"
echo === Mapas ETP continuos ===
echo Base: %BASE%
echo Python: %PY%
echo Log: %LOG%
echo.

(
  echo === Mapas ETP continuos ===
  echo Base: %BASE%
  echo METEO_ENV_FILE: %METEO_ENV_FILE%
  if not "%FECHA_ARG%"=="" echo Fecha: %FECHA_ARG%
  echo.
  if "%FECHA_ARG%"=="" (
    "%PY%" -u "%SCRIPT%"
  ) else (
    "%PY%" -u "%SCRIPT%" --fecha "%FECHA_ARG%"
  )
) >> "%LOG%" 2>&1
set "EC=!ERRORLEVEL!"

echo ExitCode: !EC!>> "%LOG%"
type "%LOG%"

echo.
if not "!EC!"=="0" (
  echo [ERROR] Fallo. Log: %LOG%
  pause
  exit /b 1
)
echo [OK] Terminado.
pause
exit /b 0
