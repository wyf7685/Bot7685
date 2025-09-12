#! /usr/bin/env sh
set -e

if [ ! -d "${VIRTUAL_ENV}" ]; then
  uv venv "${VIRTUAL_ENV}"
fi
uv sync --locked --active --no-dev

# Start Gunicorn
gunicorn -k "uvicorn.workers.UvicornWorker" -c "/gunicorn_conf.py" "bot:app"
