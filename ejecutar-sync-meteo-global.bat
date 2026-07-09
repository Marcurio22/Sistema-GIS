@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM Ejecuta sync meteo global (Inforiego -> gisdb -> replica a comunidades)
REM Uso:
REM   ejecutar-sync-meteo-global.bat [C:\GIS\comunidades\Sistema-GIS-main]
REM Si no se pasa argumento, usa la carpeta de este .bat.

set "BASE=%~1"
if "%BASE%"=="" set "BASE=%~dp0"
if "!BASE:~-1!"=="\" set "BASE=!BASE:~0,-1!"

if not exist "%BASE%\src\scripts\prediccion\sync_meteo_global.py" (
  echo.
  echo [ERROR] No es una plantilla valida (falta sync_meteo_global.py): %BASE%
  goto :fin_error
)

set "METEO_ENV_FILE=%BASE%\.env"

REM --- Entorno conda gis (mismo que "conda activate gis") ---
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
echo Log:    %LOG%
echo.

if "%NO_PAUSE%"=="1" (
  REM Tarea programada: sin consola, todo al log
  "%PY%" -u -m scripts.prediccion.sync_meteo_global >> "%LOG%" 2>&1
  set "EC=!ERRORLEVEL!"
) else (
  REM Manual: mostrar en pantalla
  "%PY%" -u -m scripts.prediccion.sync_meteo_global
  set "EC=!ERRORLEVEL!"
)

echo ExitCode: !EC!>> "%LOG%"
echo.
if not "!EC!"=="0" goto :fin_error
echo [OK] Sync meteo global terminado. Log: %LOG%
if "%NO_PAUSE%"=="1" exit /b 0
pause
exit /b 0

:fin_error
echo.
echo [ERROR] Sync meteo global fallo. Revisa el mensaje de arriba.
if "%NO_PAUSE%"=="1" exit /b 1
pause
exit /b 1
