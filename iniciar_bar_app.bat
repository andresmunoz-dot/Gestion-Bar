@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ============================================================
echo   Barrica POS - Iniciador portable para cualquier equipo
echo ============================================================

set "VENV_OK=0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import flask, bcrypt, mysql.connector, dotenv" >nul 2>&1
    if not errorlevel 1 set "VENV_OK=1"
)

if "%VENV_OK%"=="0" (
    echo.
    echo [1/2] Preparando entorno Python local para este equipo...
    if exist ".venv" (
        echo       Actualizando .venv para la ruta de este computador...
        rmdir /s /q ".venv"
    )

    set "SYS_PY="
    py -3 --version >nul 2>&1 && set "SYS_PY=py -3"
    if not defined SYS_PY if exist "%LOCALAPPDATA%\Python\bin\py.exe" set "SYS_PY="%LOCALAPPDATA%\Python\bin\py.exe" -3"
    if not defined SYS_PY (
        for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
            if exist "%%~fD\python.exe" set "SYS_PY="%%~fD\python.exe""
        )
    )
    if not defined SYS_PY (
        python -m pip --version >nul 2>&1 && set "SYS_PY=python"
    )

    if not defined SYS_PY (
        echo.
        echo [AVISO] Python 3 no esta instalado en este equipo.
        echo Abriendo bar_app.html directamente en Modo Local sin servidor...
        start "" "%~dp0bar_app.html"
        pause
        exit /b 0
    )

    !SYS_PY! -m venv .venv
    if errorlevel 1 (
        echo [AVISO] No se pudo crear .venv. Abriendo bar_app.html en Modo Local...
        start "" "%~dp0bar_app.html"
        pause
        exit /b 0
    )

    echo [2/2] Instalando dependencias en .venv...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [AVISO] No se pudieron descargar las dependencias.
        echo Abriendo bar_app.html directamente en Modo Local...
        start "" "%~dp0bar_app.html"
        pause
        exit /b 0
    )
)

if not exist ".env" (
    if exist ".env.example" (
        copy /y ".env.example" ".env" >nul
        echo [INFO] Archivo .env creado desde .env.example.
    )
)

echo.
echo [OK] Abriendo http://127.0.0.1:5000/bar_app en el navegador...
start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:5000/bar_app'"
".venv\Scripts\python.exe" app.py
pause

