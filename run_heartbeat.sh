#!/bin/bash
# RSS Heartbeat Wrapper Script
# Loads environment and executes the config-driven heartbeat.
# Designed to be called by launchd or manually.

set -e

# Get the directory where this script lives
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Load .env if it exists (for GITHUB_TOKEN, etc.)
if [ -f ".env" ]; then
    export $(cat .env | xargs)
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

# Ensure dependencies are installed
echo "📦 Syncing dependencies..."
$UV_PATH pip sync requirements.txt

# Run the Python script
# The script itself will load config.yaml
$UV_PATH run python rss_heartbeat.py

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ Heartbeat completed successfully at $(date)"
else
    echo "❌ Heartbeat failed with exit code $EXIT_CODE at $(date)"
fi

exit $EXIT_CODE
