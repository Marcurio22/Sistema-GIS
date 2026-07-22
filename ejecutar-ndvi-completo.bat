@echo off
REM NDVI composite completo (ndvi_completo.py).
REM Uso MANUAL (deja la ventana abierta si falla):
REM   cd C:\GIS\comunidades\mi_comunidad
REM   ejecutar-ndvi-completo.bat
REM Programador de tareas: usar run-ndvi-completo.bat (sin pause).
setlocal EnableExtensions EnableDelayedExpansion

set "DIR=%~1"
if "%DIR%"=="" set "DIR=%~dp0"
if "!DIR:~-1!"=="\" set "DIR=!DIR:~0,-1!"

if not exist "%DIR%\src\ndvi_completo.py" (
  echo.
  echo [ERROR] No es una comunidad GIS ^(falta src\ndvi_completo.py^):
  echo   %DIR%
  echo Uso: cd C:\GIS\comunidades\mi_comunidad ^&^& ejecutar-ndvi-completo.bat
  goto :fin_error
)

REM --- Entorno conda gis ---
set "ENV_ROOT=C:\Users\UBU\anaconda3\envs\gis"
set "PY=%ENV_ROOT%\python.exe"
if not exist "%PY%" (
  echo [AVISO] No encontrado %ENV_ROOT%\python.exe — uso python del PATH
  set "PY=python"
)

if exist "%ENV_ROOT%\python.exe" (
  set "PATH=%ENV_ROOT%;%ENV_ROOT%\Library\mingw-w64\bin;%ENV_ROOT%\Library\usr\bin;%ENV_ROOT%\Library\bin;%ENV_ROOT%\Scripts;%ENV_ROOT%\bin;%PATH%"
)
if exist "%ENV_ROOT%\Library\share\proj" set "PROJ_LIB=%ENV_ROOT%\Library\share\proj"
if exist "%ENV_ROOT%\Library\share\gdal" set "GDAL_DATA=%ENV_ROOT%\Library\share\gdal"
set "PYTHONUNBUFFERED=1"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

if not exist "%DIR%\logs" mkdir "%DIR%\logs"
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set "STAMP=%%i"
if "%STAMP%"=="" set "STAMP=%RANDOM%"
set "LOG=%DIR%\logs\ndvi-completo-%STAMP%.log"

cd /d "%DIR%\src" || (
  echo [ERROR] No se pudo entrar en %DIR%\src
  goto :fin_error
)

echo === NDVI completo ===
echo Carpeta: %DIR%
echo Python:  %PY%
echo Script:  %DIR%\src\ndvi_completo.py
echo Log:     %LOG%
echo.
echo La salida se guarda en el log. Si falla, la ventana no se cierra.
echo.

(
  echo === NDVI completo %DATE% %TIME% ===
  echo Carpeta: %DIR%
  echo Python:  %PY%
  echo.
) > "%LOG%"

"%PY%" -u ndvi_completo.py >> "%LOG%" 2>&1
set "EC=%ERRORLEVEL%"

echo.>> "%LOG%"
echo ExitCode: %EC%>> "%LOG%"

echo.
echo ---------- Ultimas lineas del log ----------
powershell -NoProfile -Command "Get-Content -LiteralPath '%LOG%' -Tail 40 -ErrorAction SilentlyContinue"
echo --------------------------------------------
echo Log completo: %LOG%
echo ExitCode: %EC%
echo.

if %EC% neq 0 goto :fin_error
echo [OK] NDVI completo terminado.
goto :fin_ok

:fin_error
echo.
echo [ERROR] NDVI completo fallo. Abre el log:
echo   %LOG%
if /I "%NO_PAUSE%"=="1" exit /b 1
echo.
pause
exit /b 1

:fin_ok
if /I "%NO_PAUSE%"=="1" exit /b 0
echo.
pause
exit /b 0
