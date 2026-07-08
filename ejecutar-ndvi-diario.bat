@echo off
REM Pack diario: ndvi_diax + generate_thumbnails
REM Uso: ejecutar-ndvi-diario.bat C:\GIS\comunidades\arlanz
setlocal EnableExtensions
set "DIR=%~1"
if "%DIR%"=="" set "DIR=%CD%"
if not exist "%DIR%\server.py" (
  echo.
  echo No es una instancia GIS ^(falta server.py^): %DIR%
  echo Uso: ejecutar-ndvi-diario.bat C:\GIS\comunidades\arlanz
  goto :fin_error
)

set "PY=C:\Users\UBU\anaconda3\envs\gis\python.exe"
if not exist "%PY%" set "PY=python"

REM PROJ/GDAL del entorno conda (igual que NSSM en crear-comunidad.ps1)
set "ENV_ROOT=C:\Users\UBU\anaconda3\envs\gis"
if exist "%ENV_ROOT%\Library\share\proj" set "PROJ_LIB=%ENV_ROOT%\Library\share\proj"
if exist "%ENV_ROOT%\Library\share\gdal" set "GDAL_DATA=%ENV_ROOT%\Library\share\gdal"
set "PYTHONUNBUFFERED=1"

cd /d "%DIR%"
echo.
echo === Pack NDVI diario ===
echo Carpeta: %DIR%
echo Python:  %PY%
if defined PROJ_LIB echo PROJ_LIB: %PROJ_LIB%
echo.

"%PY%" -u src\scripts\pack_ndvi_diario.py
if errorlevel 1 goto :fin_error
echo.
echo [OK] Terminado. Log en %DIR%\logs\
goto :fin_ok

:fin_error
echo.
echo [ERROR] Revisa el log en %DIR%\logs\pack-ndvi-diario-*.log
if "%NO_PAUSE%"=="1" goto :fin_error_nopause
pause
:fin_error_nopause
exit /b 1

:fin_ok
if "%NO_PAUSE%"=="1" goto :fin_ok_nopause
pause
:fin_ok_nopause
exit /b 0
