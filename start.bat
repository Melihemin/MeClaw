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
if errorlevel 1 (
    echo Ollama not found. Ollama provider will be unavailable; OpenAI can still be used.
) else (
    echo Starting Ollama service...
    start "Ollama" /B ollama serve
)

echo Starting MeClaw server...
start "" cmd /c "timeout /t 2 >nul & start http://127.0.0.1:8000"
python server.py
