@echo off
REM Pack diario: ndvi_diax + generate_thumbnails
REM Uso: ejecutar-ndvi-diario.bat C:\GIS\comunidades\arlanz
setlocal EnableExtensions
set "DIR=%~1"
if "%DIR%"=="" (
  set "DIR=%~dp0"
  if "%DIR:~-1%"=="\" set "DIR=%DIR:~0,-1%"
)
if not exist "%DIR%\server.py" (
  echo.
  echo No es una instancia GIS ^(falta server.py^): %DIR%
  echo Uso: ejecutar-ndvi-diario.bat C:\GIS\comunidades\arlanz
  goto :fin_error
)

set "PY=C:\Users\UBU\anaconda3\envs\gis\python.exe"
if not exist "%PY%" set "PY=python"

REM Entorno conda completo (PATH + PROJ/GDAL). Sin Library\bin, rasterio/GDAL
REM pueden crashear al lanzar desde el Programador de tareas (codigo 0xC06D007F).
set "ENV_ROOT=C:\Users\UBU\anaconda3\envs\gis"
if exist "%ENV_ROOT%\python.exe" (
  set "PATH=%ENV_ROOT%;%ENV_ROOT%\Library\mingw-w64\bin;%ENV_ROOT%\Library\usr\bin;%ENV_ROOT%\Library\bin;%ENV_ROOT%\Scripts;%ENV_ROOT%\bin;%PATH%"
)
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
set "EC=%ERRORLEVEL%"
REM Con crashes nativos (0xC06D007F) ERRORLEVEL puede ser negativo:
REM "if errorlevel 1" falla y el Programador marca la tarea como OK.
if not "%EC%"=="0" goto :fin_error
echo.
echo [OK] Terminado. Log en %DIR%\logs\
goto :fin_ok

:fin_error
echo.
echo [ERROR] codigo=%EC%. Revisa el log en %DIR%\logs\pack-ndvi-diario-*.log
if "%NO_PAUSE%"=="1" goto :fin_error_nopause
pause
:fin_error_nopause
exit /b 1

:fin_ok
if "%NO_PAUSE%"=="1" goto :fin_ok_nopause
pause
:fin_ok_nopause
exit /b 0
