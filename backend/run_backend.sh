#!/usr/bin/env bash
# run_backend.sh - Startup helper for the SIH26083 Flask backend

# Exit immediately if a command exits with a non-zero status.
set -e

# Change directory to the location of this script (backend/)
cd "$(dirname "$0")"

echo "============================================="
echo " SIH26083 Backend Startup"
echo "============================================="

# 1. Activate virtual environment if it exists
if [ -d "../.venv" ]; then
    echo "=> Activating project virtual environment (../.venv)..."
    source ../.venv/bin/activate
elif [ -d ".venv" ]; then
    echo "=> Activating local virtual environment (.venv)..."
    source .venv/bin/activate
else
    echo "=> No virtual environment found, using system Python."
fi

# 2. Load environment variables from .env if present
if [ -f ".env" ]; then
    echo "=> Loading configuration from .env..."
    export $(grep -v '^#' .env | xargs)
fi

# 3. Ensure the scheduler is explicitly enabled if not set in .env
if [ -z "$WEATHER_SCHEDULER_ENABLED" ]; then
    echo "=> WEATHER_SCHEDULER_ENABLED not set, defaulting to true."
    export WEATHER_SCHEDULER_ENABLED=true
else
    echo "=> WEATHER_SCHEDULER_ENABLED is set to $WEATHER_SCHEDULER_ENABLED."
fi

# 4. Start the Flask application
echo "=> Starting Flask backend..."
python3 app.py
