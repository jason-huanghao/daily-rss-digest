#!/bin/bash
# RSS Heartbeat Wrapper Script
# Loads environment and executes the config-driven heartbeat.
# Designed to be called by launchd or manually.

set -e

# Get the directory where this script lives
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Note: GITHUB_TOKEN should be set in launchd plist EnvironmentVariables
# or in your shell profile (~/.zshrc or ~/.bash_profile)
# For GitHub sync to work, set: export GITHUB_TOKEN=your_token_here

if [ -z "$GITHUB_TOKEN" ]; then
    echo "⚠️ Warning: GITHUB_TOKEN not set. GitHub sync disabled."
fi

# Find uv (try common paths)
UV_PATH=""
if command -v uv &> /dev/null; then
    UV_PATH=$(which uv)
elif [ -f "$HOME/.local/bin/uv" ]; then
    UV_PATH="$HOME/.local/bin/uv"
else
    echo "❌ Error: 'uv' not found. Please install uv."
    exit 1
fi

echo "🚀 Starting RSS Heartbeat at $(date)"
echo "📂 Working Directory: $SCRIPT_DIR"
echo "🔧 Using UV: $UV_PATH"

# Create/ensure local virtualenv
VENV_PATH="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV_PATH" ]; then
    echo "🔧 Creating virtual environment..."
    $UV_PATH venv "$VENV_PATH"
fi

# Ensure dependencies are installed
echo "📦 Installing dependencies..."
$UV_PATH pip install --python "$VENV_PATH/bin/python" -r requirements.txt

# Run the Python script
# The script itself will load config.yaml
"$VENV_PATH/bin/python" rss_heartbeat.py

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ Heartbeat completed successfully at $(date)"
else
    echo "❌ Heartbeat failed with exit code $EXIT_CODE at $(date)"
fi

exit $EXIT_CODE
