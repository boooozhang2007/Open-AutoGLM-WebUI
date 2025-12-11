@echo off
setlocal

echo [INFO] Checking environment...

REM Check if uv is installed
where uv >nul 2>nul
if %errorlevel% neq 0 (
    echo [WARN] 'uv' is not installed. Installing uv...
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install uv. Please install it manually: https://github.com/astral-sh/uv
        pause
        exit /b 1
    )
    REM Refresh environment variables for the current session
    set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
)

REM Check if .env exists
if not exist .env (
    echo [INFO] Creating .env from .env.example...
    copy .env.example .env
    echo [INFO] Please edit .env to configure your API keys if needed.
)

echo [INFO] Installing dependencies and starting WebUI...
uv run web_server.py

pause