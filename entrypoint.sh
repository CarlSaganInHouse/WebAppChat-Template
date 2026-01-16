#!/bin/bash
# WebAppChat entrypoint - fixes bind mount permissions on startup

set -e

# Fix ownership of bind-mounted /app directory
# This handles files created/edited as root on the host
echo "[entrypoint] Fixing /app permissions for appuser (1002)..."
chown -R appuser:appuser /app 2>/dev/null || true

# Also fix the vault mount if it exists and has permission issues
if [ -d "/app/vault" ]; then
    echo "[entrypoint] Checking /app/vault permissions..."
    # Only fix files owned by root, preserve other ownership
    find /app/vault -user root -exec chown appuser:appuser {} \; 2>/dev/null || true
fi

echo "[entrypoint] Starting application as appuser..."

# Drop privileges and run the application
exec gosu appuser python app.py
