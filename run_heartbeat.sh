#!/bin/bash
# Robust Wrapper for RSS Heartbeat (Launchd Compatible)
# Uses absolute paths to avoid launchd PATH issues.

# 1. Get the directory where this script lives (Repo Root)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# 2. Explicit PATH (Critical for launchd)
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:/Users/mac/Documents/nanobot/.venv/bin:$PATH"

# 3. Define Paths
PYTHON_BIN="/Users/mac/Documents/nanobot/.venv/bin/python"
SCRIPT_PATH="$SCRIPT_DIR/rss_heartbeat.py"
ENV_FILE="$SCRIPT_DIR/../.env" # Load .env from parent directory (secure)

# 4. Load Environment Variables (if exists)
if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
else
    echo "⚠️ Warning: .env not found at $ENV_FILE. GitHub auth may fail." >&2
fi

# 5. Change to Repo Directory
cd "$SCRIPT_DIR" || exit 1

# 6. Execute directly with absolute python binary
# No 'uv run', no 'source activate', no logs (Logless Architecture)
"$PYTHON_BIN" "$SCRIPT_PATH"