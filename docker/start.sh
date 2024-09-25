#! /usr/bin/env sh
set -e


if [ ! -f /bot7685.initialize.flag ]; then
  BOT7685_UID=${BOT7685_UID:=911}
  BOT7685_GID=${BOT7685_GID:=1001}
  usermod -o -u ${BOT7685_UID} bot7685
  groupmod -o -g ${BOT7685_GID} bot7685
  usermod -g ${BOT7685_GID} bot7685
  chown -R ${BOT7685_UID}:${BOT7685_GID} /app
  touch /bot7685.initialize.flag
fi

if [ -f /app/app/main.py ]; then
  DEFAULT_MODULE_NAME=app.main
elif [ -f /app/main.py ]; then
  DEFAULT_MODULE_NAME=main
fi
MODULE_NAME=${MODULE_NAME:-$DEFAULT_MODULE_NAME}
VARIABLE_NAME=${VARIABLE_NAME:-app}
export APP_MODULE=${APP_MODULE:-"$MODULE_NAME:$VARIABLE_NAME"}

if [ -f /app/gunicorn_conf.py ]; then
  DEFAULT_GUNICORN_CONF=/app/gunicorn_conf.py
elif [ -f /app/app/gunicorn_conf.py ]; then
  DEFAULT_GUNICORN_CONF=/app/app/gunicorn_conf.py
else
  DEFAULT_GUNICORN_CONF=/gunicorn_conf.py
fi
export GUNICORN_CONF=${GUNICORN_CONF:-$DEFAULT_GUNICORN_CONF}
export WORKER_CLASS=${WORKER_CLASS:-"uvicorn.workers.UvicornWorker"}

# If there's a prestart.sh script in the /app directory or other path specified, run it before starting
PRE_START_PATH=${PRE_START_PATH:-/app/prestart.sh}
echo "Checking for script in $PRE_START_PATH"
if [ -f $PRE_START_PATH ]; then
  echo "Running script $PRE_START_PATH"
  . "$PRE_START_PATH"
else
  echo "There is no script $PRE_START_PATH"
fi

# Start Gunicorn
gosu bot7685 gunicorn -k "$WORKER_CLASS" -c "$GUNICORN_CONF" "$APP_MODULE"
