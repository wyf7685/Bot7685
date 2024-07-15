FROM python:3.12 AS wheels

WORKDIR /wheel

COPY ./requirements.txt /wheel/
RUN python -m pip wheel --wheel-dir=/wheel --no-cache-dir --requirement ./requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

FROM python:3.12-slim-bookworm AS app

WORKDIR /app
ENV TZ=Asia/Shanghai
ENV PYTHONPATH=/app
ENV APP_MODULE=bot:app
ENV MAX_WORKERS=1

COPY ./docker/gunicorn_conf.py ./docker/start.sh /
COPY ./docker/fonts /usr/share/fonts/meme-fonts
# from https://github.com/MeetWq/meme-generator/blob/main/Dockerfile
RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    apt-get install -y --no-install-recommends locales fontconfig fonts-noto-color-emoji gettext && \
    localedef -i zh_CN -c -f UTF-8 -A /usr/share/locale/locale.alias zh_CN.UTF-8 && \
    fc-cache -fv && \
    apt-get purge -y --auto-remove && \
    apt clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

COPY --from=wheels /wheel /wheel
RUN python -m pip install --no-cache-dir --no-index --force-reinstall --find-links=/wheel -r /wheel/requirements.txt && \
    /usr/local/bin/meme download && \
    rm -rf /wheel /root/.config/meme_generator/ && \
    chmod +x /start.sh

VOLUME [ "/app", "/root/.config/meme_generator" ]
CMD [ "/start.sh" ]
