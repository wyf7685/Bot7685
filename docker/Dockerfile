FROM python:3.12 AS wheels

WORKDIR /wheel
COPY ./requirements.txt /wheel/
RUN python -m pip wheel --wheel-dir=/wheel --no-cache-dir --requirement ./requirements.txt

FROM wyf7685/bot7685:base AS app

WORKDIR /app

ENV PYTHONPATH=/app
ENV APP_MODULE=bot:app
ENV MAX_WORKERS=1

COPY ./gunicorn_conf.py ./start.sh /
RUN chmod +x /start.sh

COPY --from=wheels /wheel /wheel
RUN python -m pip install --no-cache-dir --no-index --force-reinstall --root-user-action --find-links=/wheel -r /wheel/requirements.txt && \
    rm -rf /wheel

VOLUME [ "/app" ]
CMD [ "bash", "/start.sh" ]
