#!/bin/bash
set -e
echo "[Vox] Running database migrations..."
python manage.py migrate --no-input
echo "[Vox] Starting Daphne..."
exec daphne -b 0.0.0.0 -p 8000 backend.asgi:application
