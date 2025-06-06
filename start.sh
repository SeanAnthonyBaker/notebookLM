#!/bin/bash

echo "Starting container cleanup and FastAPI application..."

# Aggressive cleanup of common Chrome/Chromedriver temp directories
# These are locations where Chrome/Chromedriver might store profiles/data
# and leave locks, especially if previous runs crashed.
echo "Cleaning up potential orphaned Chrome/Chromedriver user data directories..."

# Clean up directories in /tmp (where mkdtemp might create them)
rm -rf /tmp/selenium_profile_*
rm -rf /tmp/.com.google.Chrome.*

# Clean up default Chrome user data directory (if it exists)
# The selenium/standalone-chrome image might have a default or fallback location.
# This path is common for Chrome user profiles.
rm -rf /home/seluser/.config/google-chrome/Default # The 'Default' profile within user data
rm -rf /home/seluser/.config/google-chrome/SingletonLock # Common lock file

# Ensure permissions are correct just in case (though Dockerfile already sets /tmp)
chmod -R 777 /tmp

# --- Ensure Virtual Environment and Dependencies are Setup ---
# Check if the virtual environment exists
if [ ! -d "/app/.venv" ]; then
    echo "Virtual environment not found at /app/.venv. Creating..."
    python -m venv /app/.venv
    echo "Installing dependencies into the virtual environment..."
    /app/.venv/bin/pip install --no-cache-dir -r /app/requirements.txt
fi

echo "Cleanup complete. Starting FastAPI application..."
# Activate the virtual environment within the app directory
source /app/.venv/bin/activate

# Execute the FastAPI application
exec uvicorn main:app --host 0.0.0.0 --port 8000