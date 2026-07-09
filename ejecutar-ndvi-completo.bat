@echo off
REM NDVI composite completo (ndvi_completo.py). Requiere admin por bloqueos de ficheros en Windows.
REM Uso desde la carpeta de la comunidad:
REM   ejecutar-ndvi-completo.bat
REM Tambien acepta ruta explicita:
REM   ejecutar-ndvi-completo.bat C:\GIS\comunidades\mi_comunidad
setlocal EnableExtensions

set "DIR=%~1"
if "%DIR%"=="" (
  set "DIR=%~dp0"
  if "%DIR:~-1%"=="\" set "DIR=%DIR:~0,-1%"
)

net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Solicitando permisos de administrador...
  set "VBS=%TEMP%\_gis_uac_ndvi.vbs"
  > "%VBS%" echo Set UAC = CreateObject^("Shell.Application"^)
  >>"%VBS%" echo UAC.ShellExecute "%~f0", "%DIR%", "", "runas", 1
  cscript //nologo "%VBS%" >nul 2>&1
  del "%VBS%" >nul 2>&1
  exit /b
)

if not exist "%DIR%\server.py" (
  echo.
  echo No es una comunidad GIS ^(falta server.py^): %DIR%
  echo Uso: cd C:\GIS\comunidades\mi_comunidad ^&^& ejecutar-ndvi-completo.bat
  goto :fin_error
)

set "PY=C:\Users\UBU\anaconda3\envs\gis\python.exe"
if not exist "%PY%" set "PY=python"

set "ENV_ROOT=C:\Users\UBU\anaconda3\envs\gis"
if exist "%ENV_ROOT%\Library\share\proj" set "PROJ_LIB=%ENV_ROOT%\Library\share\proj"
if exist "%ENV_ROOT%\Library\share\gdal" set "GDAL_DATA=%ENV_ROOT%\Library\share\gdal"
set "PYTHONUNBUFFERED=1"
set "PYTHONUTF8=1"

if not exist "%DIR%\logs" mkdir "%DIR%\logs"
for /f "tokens=1-4 delims=/-. " %%a in ("%date%") do set "STAMP=%%d-%%b-%%c"
set "LOG=%DIR%\logs\ndvi-completo-%STAMP%.log"

cd /d "%DIR%"
echo === NDVI completo ===
echo Carpeta: %DIR%
echo Python:  %PY%
echo Log:     %LOG%
echo.

if "%NO_PAUSE%"=="1" (
  powershell.exe -NoProfile -Command ^
    "& { $py = '%PY%'; $log = '%LOG%'; " ^
    "'=== NDVI completo ===' | Out-File -FilePath $log -Encoding utf8; " ^
    "'Carpeta: %DIR%' | Out-File -FilePath $log -Append -Encoding utf8; " ^
    "& $py -u src\ndvi_completo.py 2>&1 | Tee-Object -FilePath $log -Append; " ^
    "exit $LASTEXITCODE }"
  set "EC=%ERRORLEVEL%"
) else (
  echo === NDVI completo === >> "%LOG%"
  echo Carpeta: %DIR% >> "%LOG%"
  echo Python: %PY% >> "%LOG%"
  echo. >> "%LOG%"
  "%PY%" -u src\ndvi_completo.py >> "%LOG%" 2>&1
  set "EC=%ERRORLEVEL%"
)

echo ExitCode: %EC% >> "%LOG%"
if %EC% neq 0 goto :fin_error
echo [OK] Terminado. Log: %LOG%
goto :fin_ok

:fin_error
echo [ERROR] Revisa %LOG%
if "%NO_PAUSE%"=="1" exit /b 1
pause
exit /b 1

:fin_ok
if "%NO_PAUSE%"=="1" exit /b 0
pause
exit /b 0
