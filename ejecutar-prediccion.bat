@echo off
setlocal EnableExtensions
title GIS - Prediccion run_all

echo.
echo ============================================================
echo  Prediccion run_all (manual)
echo ============================================================
echo.

set "DIR=%~1"
if "%DIR%"=="" set "DIR=%~dp0"
pushd "%DIR%" 2>nul
if errorlevel 1 (
  echo [ERROR] Carpeta no valida: %DIR%
  pause
  exit /b 1
)
set "DIR=%CD%"
popd

echo Comunidad: %DIR%
echo.

if not exist "%DIR%\server.py" (
  echo [ERROR] No es comunidad GIS (falta server.py): %DIR%
  echo Ejecuta desde la carpeta de la comunidad, ej. C:\GIS\comunidades\crd2
  pause
  exit /b 1
)

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
set "PYTHONPATH=%DIR%\src"

if not exist "%DIR%\logs" mkdir "%DIR%\logs"
for /f "tokens=1-4 delims=/-. " %%a in ("%date%") do set "STAMP=%%d-%%b-%%c"
set "LOG=%DIR%\logs\prediccion-runall-%STAMP%.log"

cd /d "%DIR%"
echo === Prediccion run_all ===
echo Comunidad: %DIR%
echo Python:  %PY%
echo Log:     %LOG%
echo.

set "SCRIPT=%DIR%\src\scripts\prediccion\run_all.py"
if exist "%SCRIPT%" (
  "%PY%" -u "%SCRIPT%"
) else (
  "%PY%" -u -m scripts.prediccion.run_all
)
set "EC=%ERRORLEVEL%"

echo.
echo ExitCode: %EC%
echo Log: %LOG%
if %EC% neq 0 (
  echo [ERROR] Prediccion fallo.
) else (
  echo [OK] Prediccion terminada.
)
pause
exit /b %EC%
