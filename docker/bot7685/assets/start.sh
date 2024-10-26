#! /usr/bin/env sh
set -e

if [ ! -f /bot7685.initialize.flag ]; then
  chown -R ${UID}:${GID} /app
  touch /bot7685.initialize.flag
fi

# Start Gunicorn
gunicorn -k "uvicorn.workers.UvicornWorker" -c "/gunicorn_conf.py" "bot:app"
