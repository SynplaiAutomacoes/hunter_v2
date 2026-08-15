#!/bin/sh
set -e

# APP_PROCESS controls which process this container runs:
#   web       -> Gunicorn (default, Django HTTP)
#   realtime  -> Daphne ASGI (WebSocket + dispatch status ingest)
#               + background poller for due outbound/appointment alerts
APP_PROCESS="${APP_PROCESS:-web}"
PORT="${PORT:-8000}"
OUTBOUND_POLLER_INTERVAL_SECONDS="${OUTBOUND_POLLER_INTERVAL_SECONDS:-60}"
OUTBOUND_POLLER_TICK_TIMEOUT_SECONDS="${OUTBOUND_POLLER_TICK_TIMEOUT_SECONDS:-55}"
OUTBOUND_POLLER_MAX_CONSECUTIVE_FAILURES="${OUTBOUND_POLLER_MAX_CONSECUTIVE_FAILURES:-5}"

echo "Ensuring NF-e emission columns..."
uv run python manage.py ensure_nferequest_emission_columns

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
    echo "Starting outbound poller (every ${OUTBOUND_POLLER_INTERVAL_SECONDS}s, tick timeout ${OUTBOUND_POLLER_TICK_TIMEOUT_SECONDS}s)..."
    REALTIME_SHELL_PID=$$
    (
      consecutive_failures=0
      while true; do
        if timeout "${OUTBOUND_POLLER_TICK_TIMEOUT_SECONDS}" uv run python manage.py run_due_outbound_messages; then
          consecutive_failures=0
          echo "outbound_poller_tick_ok"
        else
          consecutive_failures=$((consecutive_failures + 1))
          echo "outbound_poller_tick_failed count=${consecutive_failures}"
          if [ "${consecutive_failures}" -ge "${OUTBOUND_POLLER_MAX_CONSECUTIVE_FAILURES}" ]; then
            echo "outbound_poller_giving_up after ${consecutive_failures} consecutive failures"
            kill -TERM "${REALTIME_SHELL_PID}" 2>/dev/null || true
            exit 1
          fi
        fi
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
