@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM Sync meteo global desde la plantilla Sistema-GIS-main.
REM Uso: ejecutar-sync-meteo-global.bat

set "BASE=%~1"
if "%BASE%"=="" set "BASE=%~dp0"
if "!BASE:~-1!"=="\" set "BASE=!BASE:~0,-1!"

set "SCRIPT=%BASE%\src\scripts\prediccion\sync_meteo_global.py"
if not exist "%SCRIPT%" (
  echo.
  echo [ERROR] No existe: %SCRIPT%
  goto :fin_error
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
set "LOG=%BASE%\logs\sync-meteo-global-%STAMP%.log"

cd /d "%BASE%"
echo === Sync meteo global ===
echo Base:   %BASE%
echo Python: %PY%
echo Script: %SCRIPT%
echo Log:    %LOG%
echo.

(
  echo === Sync meteo global ===
  echo Base: %BASE%
  echo Python: %PY%
  echo Script: %SCRIPT%
  echo METEO_ENV_FILE: %METEO_ENV_FILE%
  echo.
  "%PY%" -u "%SCRIPT%"
) >> "%LOG%" 2>&1
set "EC=!ERRORLEVEL!"

echo ExitCode: !EC!>> "%LOG%"
type "%LOG%"

echo.
if not "!EC!"=="0" goto :fin_error
echo [OK] Sync meteo global terminado.
pause
exit /b 0

:fin_error
echo [ERROR] Sync meteo global fallo. Log: %LOG%
pause
exit /b 1
