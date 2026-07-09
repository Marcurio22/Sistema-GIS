@echo off
REM NDVI composite completo (ndvi_completo.py).
REM Uso desde la carpeta de la comunidad:
REM   ejecutar-ndvi-completo.bat
REM Tambien acepta ruta explicita:
REM   ejecutar-ndvi-completo.bat C:\GIS\comunidades\mi_comunidad
setlocal EnableExtensions EnableDelayedExpansion

set "DIR=%~1"
if "%DIR%"=="" set "DIR=%~dp0"
if "!DIR:~-1!"=="\" set "DIR=!DIR:~0,-1!"

if not exist "%DIR%\src\ndvi_completo.py" (
  echo.
  echo No es una comunidad GIS ^(falta src\ndvi_completo.py^): %DIR%
  echo Uso: cd C:\GIS\comunidades\mi_comunidad ^&^& ejecutar-ndvi-completo.bat
  goto :fin_error
)

REM --- Entorno conda gis (mismo que al hacer "conda activate gis") ---
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

if not exist "%DIR%\logs" mkdir "%DIR%\logs"
for /f "tokens=1-4 delims=/-. " %%a in ("%date%") do set "STAMP=%%d-%%b-%%c"
set "LOG=%DIR%\logs\ndvi-completo-%STAMP%.log"

cd /d "%DIR%\src"
echo === NDVI completo ===
echo Carpeta: %DIR%
echo Python:  %PY%
echo Log:     %LOG%
echo.

"%PY%" -u ndvi_completo.py
set "EC=%ERRORLEVEL%"

echo ExitCode: %EC%>> "%LOG%"
if %EC% neq 0 goto :fin_error
echo [OK] Terminado.
goto :fin_ok

:fin_error
echo.
echo [ERROR] NDVI completo fallo. Revisa el mensaje de arriba.
if "%NO_PAUSE%"=="1" exit /b 1
pause
exit /b 1

:fin_ok
if "%NO_PAUSE%"=="1" exit /b 0
pause
exit /b 0
