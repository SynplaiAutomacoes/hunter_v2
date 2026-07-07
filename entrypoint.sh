#!/bin/sh
set -e

echo "Syncronizing webhook"
uv run python manage.py webhook

echo "Running migrations..."
uv run python manage.py migrate --noinput

echo "Starting gunicorn..."
exec uv run gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --worker-class gthread \
  --workers "${GUNICORN_WORKERS:-4}" \
  --threads "${GUNICORN_THREADS:-4}" \
  --timeout "${GUNICORN_TIMEOUT:-60}" \
  --max-requests "${GUNICORN_MAX_REQUESTS:-1000}" \
  --max-requests-jitter "${GUNICORN_MAX_REQUESTS_JITTER:-100}"

