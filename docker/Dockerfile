FROM wyf7685/bot7685:base

WORKDIR /app

ENV PYTHONPATH=/app
ENV APP_MODULE=bot:app
ENV MAX_WORKERS=1

ADD docker/fonts/*.ttf /usr/share/fonts/
ADD docker/assets/* /

ENV UV_LINK_MODE=copy
ENV UV_TOOL_BIN_DIR=/opt/uv-bin/
RUN uv venv /opt/venv

ENV VIRTUAL_ENV=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$UV_TOOL_BIN_DIR:$PATH"
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --active --no-dev && \
    fc-cache -f -v && \
    chmod +x /entrypoint.sh

VOLUME [ "/app" ]
CMD [ "/bin/bash", "-c", "/entrypoint.sh" ]
