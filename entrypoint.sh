#!/bin/sh
set -e

# APP_PROCESS controls which process this container runs:
#   web       -> Gunicorn (default, Django HTTP)
#   realtime  -> Daphne ASGI (WebSocket + dispatch status ingest)
APP_PROCESS="${APP_PROCESS:-web}"
PORT="${PORT:-8000}"

echo "Running migrations..."
uv run python manage.py migrate --noinput

case "$APP_PROCESS" in
  web)
    echo "Syncronizing webhook"
    uv run python manage.py webhook

    echo "Running migrations..."
    uv run python manage.py migrate --noinput

    echo "Starting gunicorn (APP_PROCESS=web) on 0.0.0.0:${PORT}..."
    exec uv run gunicorn config.wsgi:application --config gunicorn.conf.py
    ;;
  realtime)
    echo "Starting daphne realtime ASGI (APP_PROCESS=realtime) on 0.0.0.0:${PORT}..."
    echo "Note: use a single replica (InMemoryChannelLayer)."
    exec uv run daphne -b 0.0.0.0 -p "${PORT}" config.asgi:application
    ;;
  *)
    echo "Unknown APP_PROCESS='${APP_PROCESS}'. Use 'web' or 'realtime'." >&2
    exit 1
    ;;
esac
