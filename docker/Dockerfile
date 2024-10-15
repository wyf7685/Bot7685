FROM wyf7685/bot7685:base

WORKDIR /app

ENV PYTHONPATH=/app
ENV APP_MODULE=bot:app
ENV MAX_WORKERS=1

COPY ./requirements.txt /
RUN python -m pip install --no-cache-dir --force-reinstall --root-user-action ignore -r /requirements.txt

COPY ./gunicorn_conf.py ./start.sh /
RUN chmod +x /start.sh

VOLUME [ "/app" ]
CMD [ "/bin/bash", "-c", "/start.sh" ]
