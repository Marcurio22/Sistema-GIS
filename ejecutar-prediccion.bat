@echo off
setlocal EnableExtensions EnableDelayedExpansion
title GIS - Prediccion run_all

echo.
echo ============================================================
echo  Prediccion run_all (manual)
echo ============================================================
echo.

set "DIR=%~1"
if "%DIR%"=="" set "DIR=%~dp0"
if "!DIR:~-1!"=="\" set "DIR=!DIR:~0,-1!"

pushd "!DIR!" 2>nul
if errorlevel 1 goto :err_dir
set "DIR=!CD!"
popd

echo Comunidad: !DIR!
echo.

if not exist "!DIR!\server.py" goto :err_not_community

call :resolve_python
if errorlevel 1 goto :err_pause

set "PYTHONUNBUFFERED=1"
set "PYTHONUTF8=1"
set "PYTHONPATH=!DIR!\src"

if not exist "!DIR!\logs" mkdir "!DIR!\logs"
for /f "tokens=1-3 delims=/" %%a in ("%date%") do set "STAMP=%%c-%%b-%%a"
set "LOG=!DIR!\logs\prediccion-runall-!STAMP!.log"
set "SCRIPT=!DIR!\src\scripts\prediccion\run_all.py"

cd /d "!DIR!"
echo === Prediccion run_all ===
echo Comunidad: !DIR!
echo Python:  !PY!
echo Log:     !LOG!
echo.

(
  echo === Prediccion run_all ===
  echo Comunidad: !DIR!
  echo Python: !PY!
  echo.
) >> "!LOG!"

if exist "!SCRIPT!" (
  "%PY%" -u "!SCRIPT!" >> "!LOG!" 2>&1
) else (
  "%PY%" -u -m scripts.prediccion.run_all >> "!LOG!" 2>&1
)
set "EC=!ERRORLEVEL!"

echo ExitCode: !EC!>> "!LOG!"
type "!LOG!"

echo.
echo ExitCode: !EC!
echo Log: !LOG!
if !EC! neq 0 (
  echo [ERROR] Prediccion fallo.
) else (
  echo [OK] Prediccion terminada.
)
if "!NO_PAUSE!"=="1" exit /b !EC!
pause
exit /b !EC!

:resolve_python
set "PY="
set "ENV_ROOT="
for %%P in (
  "C:\Users\UBU\anaconda3\envs\gis\python.exe"
  "C:\Users\Instalador\anaconda3\envs\gis\python.exe"
  "%USERPROFILE%\anaconda3\envs\gis\python.exe"
  "%USERPROFILE%\miniconda3\envs\gis\python.exe"
) do (
  if not defined PY if exist %%P (
    set "PY=%%~P"
    for %%E in ("%%~dpP.") do set "ENV_ROOT=%%~fE"
  )
)
if not defined PY (
  where python >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] No se encontro el entorno conda "gis".
    echo Instala Anaconda y crea el entorno, o indica la ruta en GIS_PYTHON.
    exit /b 1
  )
  set "PY=python"
  exit /b 0
)
if exist "!ENV_ROOT!\python.exe" (
  set "PATH=!ENV_ROOT!;!ENV_ROOT!\Library\mingw-w64\bin;!ENV_ROOT!\Library\usr\bin;!ENV_ROOT!\Library\bin;!ENV_ROOT!\Scripts;!ENV_ROOT!\bin;!PATH!"
)
if exist "!ENV_ROOT!\Library\share\proj" set "PROJ_LIB=!ENV_ROOT!\Library\share\proj"
if exist "!ENV_ROOT!\Library\share\gdal" set "GDAL_DATA=!ENV_ROOT!\Library\share\gdal"
exit /b 0

:err_dir
echo [ERROR] Carpeta no valida: %DIR%
goto :err_pause

:err_not_community
echo [ERROR] No es comunidad GIS (falta server.py): !DIR!
echo Ejecuta desde la carpeta de la comunidad.
echo Ejemplo de ruta: C:\GIS\comunidades\mi_comunidad
goto :err_pause

:err_pause
if "!NO_PAUSE!"=="1" exit /b 1
pause
exit /b 1
