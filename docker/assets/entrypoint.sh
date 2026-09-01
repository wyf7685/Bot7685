#!/usr/bin/env sh
set -e

if [ "$#" -gt 0 ]; then
  exec python3 bot.py "$@"
fi

export APP_MODULE="bot:app"
export MAX_WORKERS="1"

# Start Gunicorn as PID 1 so container signals reach the master process.
exec gunicorn -k "uvicorn.workers.UvicornWorker" -c "/gunicorn_conf.py" "bot:app"
