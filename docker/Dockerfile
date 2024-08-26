FROM python:3.12 AS wheels

WORKDIR /wheel
COPY ./requirements.txt /wheel/
RUN python -m pip wheel --wheel-dir=/wheel --no-cache-dir --requirement ./requirements.txt

FROM python:3.12-slim-bookworm AS app

WORKDIR /app

ENV TZ=Asia/Shanghai
ENV PYTHONPATH=/app
ENV APP_MODULE=bot:app
ENV MAX_WORKERS=1
ENV LANG=zh_CN.UTF-8
ENV LANGUAGE=zh_CN.UTF-8
ENV LC_ALL=zh_CN.UTF-8

COPY ./gunicorn_conf.py ./start.sh /
COPY --from=wheels /wheel /wheel
RUN apt-get update && \
    apt-get install -y --no-install-recommends locales locales-all fonts-noto libnss3-dev libxss1 libasound2 libxrandr2 libatk1.0-0 libgtk-3-0 libgbm-dev libxshmfence1 && \
    python -m pip install --no-cache-dir --no-index --force-reinstall --find-links=/wheel -r /wheel/requirements.txt && \
    rm -rf /wheel && \
    chmod +x /start.sh && \
    playwright install chromium && playwright install-deps &&\
    apt-get purge -y --auto-remove && \
    rm -rf /var/lib/apt/lists/*

VOLUME [ "/app" ]
CMD [ "/start.sh" ]
