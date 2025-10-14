FROM wyf7685/bot7685:base AS app

WORKDIR /app

ENV TZ=Asia/Shanghai \
    LANG=zh_CN.UTF-8 \
    LANGUAGE=zh_CN:en_US \
    PYTHONPATH=/app \
    VIRTUAL_ENV=/opt/venv \
    UV_LINK_MODE=copy \
    UV_CACHE_DIR=/opt/uv-cache \
    UV_PYTHON_INSTALL_DIR=/opt/python \
    PATH="/opt/venv/bin:$PATH"

COPY docker/assets/* /
RUN chmod +x /entrypoint.sh

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
RUN uv python install 3.14 --no-cache

VOLUME [ "/app", "/opt/venv", "/opt/uv-cache" ]
CMD [ "/bin/sh", "-c", "/entrypoint.sh" ]
