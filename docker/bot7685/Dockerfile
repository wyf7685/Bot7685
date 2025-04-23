FROM wyf7685/bot7685:base

WORKDIR /app

ENV PYTHONPATH=/app
ENV APP_MODULE=bot:app
ENV MAX_WORKERS=1

ENV UV_SYSTEM_PYTHON=1
ENV UV_LINK_MODE=copy
ENV UV_TOOL_BIN_DIR=/opt/uv-bin/
ENV PATH="/opt/uv-bin/:$PATH"

ADD docker/bot7685/fonts/*.ttf /usr/share/fonts/
ADD docker/bot7685/assets/* /
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked && \
    fc-cache -f -v && \
    chmod +x /start.sh

VOLUME [ "/app" ]
CMD [ "/bin/bash", "-c", "/start.sh" ]
