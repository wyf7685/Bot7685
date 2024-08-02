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
COPY --from=wheels /wheel /wheel
RUN python -m pip install --no-cache-dir --no-index --force-reinstall --find-links=/wheel -r /wheel/requirements.txt && \
    rm -rf /wheel && \
    chmod +x /start.sh

VOLUME [ "/app" ]
CMD [ "/start.sh" ]
