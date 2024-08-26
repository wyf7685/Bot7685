FROM node:22-bookworm-slim

ARG DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Shanghai

RUN apt-get update -y \
    && apt-get install -y --no-install-recommends ca-certificates curl git redis-server chromium libgtk-3-0 libasound2 libgbm1 libnss3 locales \
    && localedef -i zh_CN -c -f UTF-8 -A /usr/share/locale/locale.alias zh_CN.UTF-8 \
    && apt-get purge -y --auto-remove \
    && rm -rf /var/lib/apt/lists/* \
    && echo -e "LANG=\"zh_CN.UTF-8\"\nLANGUAGE=\"zh_CN:zh\"\nLC_NUMERIC=\"zh_CN\"\nLC_TIME=\"zh_CN\"\nLC_MONETARY=\"zh_CN\"\nLC_PAPER=\"zh_CN\"\nLC_NAME=\"zh_CN\"\nLC_ADDRESS=\"zh_CN\"\nLC_TELEPHONE=\"zh_CN\"\nLC_MEASUREMENT=\"zh_CN\"\nLC_IDENTIFICATION=\"zh_CN\"\nLC_ALL=\"zh_CN.UTF-8\"" > /etc/default/locale \
    && cat /etc/default/locale >> /etc/environment

CMD [ "/bin/bash" ]
