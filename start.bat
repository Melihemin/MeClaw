@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

where python >nul 2>nul
if errorlevel 1 (
    echo Python not found. Please install Python and try again.
    exit /b 1
)

where pip >nul 2>nul
if errorlevel 1 (
    echo pip not found. Please install pip and try again.
    exit /b 1
)

python -m pip install -r requirements.txt

where ollama >nul 2>nul
if errorlevel 0 (
    echo Starting Ollama service...
    start "Ollama" /B ollama serve
) else (
    echo Ollama not found. Please install Ollama and try again.
    exit /b 1
)

echo Starting MeClaw server...
python server.py
