#!/bin/sh
set -e

# APP_PROCESS controls which process this container runs:
#   web       -> Gunicorn (default, Django HTTP)
#   realtime  -> Daphne ASGI (WebSocket + dispatch status ingest)
#               + background poller for due outbound/appointment alerts
APP_PROCESS="${APP_PROCESS:-web}"
PORT="${PORT:-8000}"
OUTBOUND_POLLER_INTERVAL_SECONDS="${OUTBOUND_POLLER_INTERVAL_SECONDS:-60}"

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
    echo "Starting outbound poller (every ${OUTBOUND_POLLER_INTERVAL_SECONDS}s)..."
    (
      while true; do
        uv run python manage.py run_due_outbound_messages || echo "outbound_poller_tick_failed"
        sleep "${OUTBOUND_POLLER_INTERVAL_SECONDS}"
      done
    ) &
    OUTBOUND_POLLER_PID=$!
    trap 'kill "${OUTBOUND_POLLER_PID}" 2>/dev/null || true' EXIT INT TERM

    echo "Starting daphne realtime ASGI (APP_PROCESS=realtime) on 0.0.0.0:${PORT}..."
    echo "Note: use a single replica (InMemoryChannelLayer + outbound poller)."
    # Do not exec: keep this shell as parent so the poller and EXIT trap stay alive.
    uv run daphne -b 0.0.0.0 -p "${PORT}" config.asgi:application
    ;;
  *)
    echo "Unknown APP_PROCESS='${APP_PROCESS}'. Use 'web' or 'realtime'." >&2
    exit 1
    ;;
esac
