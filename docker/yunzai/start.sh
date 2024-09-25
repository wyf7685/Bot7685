#!/bin/bash

if [ ! -f /yunzai.initialize.flag ]; then
  YUNZAI_UID=${YUNZAI_UID:=911}
  YUNZAI_GID=${YUNZAI_GID:=1001}
  usermod -o -u ${YUNZAI_UID} yunzai
  groupmod -o -g ${YUNZAI_GID} yunzai
  usermod -g ${YUNZAI_GID} yunzai
  chown -R ${YUNZAI_UID}:${YUNZAI_GID} /app
  touch /yunzai.initialize.flag
fi

redis-server --port 6379 --save 900 1 --save 300 10 --daemonize yes
gosu yunzai node app
