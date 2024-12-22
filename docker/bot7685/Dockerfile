FROM wyf7685/bot7685:base

WORKDIR /app

ENV PYTHONPATH=/app
ENV APP_MODULE=bot:app
ENV MAX_WORKERS=1

COPY ./fonts/*.ttf /usr/share/fonts/
RUN fc-cache -f -v

COPY ./assets/* /
RUN python -m pip install --no-cache-dir --force-reinstall --root-user-action ignore -r /requirements.txt && \
    python /patch_satori.py && \
    chmod +x /start.sh

VOLUME [ "/app" ]
CMD [ "/bin/bash", "-c", "/start.sh" ]
