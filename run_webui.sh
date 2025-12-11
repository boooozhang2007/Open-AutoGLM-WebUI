#!/bin/bash

echo "[INFO] Checking environment..."

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "[WARN] 'uv' is not installed. Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    source $HOME/.cargo/env
fi

# Check if .env exists
if [ ! -f .env ]; then
    echo "[INFO] Creating .env from .env.example..."
    cp .env.example .env
    echo "[INFO] Please edit .env to configure your API keys if needed."
fi

echo "[INFO] Installing dependencies and starting WebUI..."
uv run web_server.py