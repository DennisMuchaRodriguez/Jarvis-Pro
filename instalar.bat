@echo off
REM Instalador de Jarvis para Windows: doble clic o ejecutalo desde la terminal de VS Code.
cd /d "%~dp0"
echo.
echo ===== Instalando J.A.R.V.I.S. =====
echo.

where py >nul 2>nul
if errorlevel 1 (
    echo [X] No encontre Python. Instala Python 3.12 desde https://www.python.org/downloads/
    echo     y marca la casilla "Add python.exe to PATH" durante la instalacion.
    pause
    exit /b 1
)

if not exist .venv (
    echo Creando el entorno virtual .venv ...
    for %%v in (3.12 3.13 3.11 3.10) do (
        if not exist .venv py -%%v -m venv .venv >nul 2>nul
    )
)
if not exist .venv\Scripts\python.exe (
    echo [X] Necesitas Python 3.10, 3.11, 3.12 o 3.13. Recomendado: 3.12 desde python.org
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [X] Fallo la instalacion de paquetes. Copia el error de arriba y compartelo.
    pause
    exit /b 1
)

if not exist .env (
    copy .env.example .env >nul
    echo.
    echo [!] Cree el archivo .env. Abrelo en VS Code y pega tu ANTHROPIC_API_KEY.
)

echo.
python verificar.py
pause
