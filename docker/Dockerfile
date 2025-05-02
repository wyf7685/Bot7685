FROM python:3.13-slim-bookworm as build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/

RUN uv venv /opt/venv
ENV UV_LINK_MODE=copy
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --active --no-dev

FROM wyf7685/bot7685:base as app

WORKDIR /app

ENV PYTHONPATH=/app
ENV APP_MODULE=bot:app
ENV MAX_WORKERS=1

ENV UV_LINK_MODE=copy
ENV UV_TOOL_BIN_DIR=/opt/uv-bin/
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$UV_TOOL_BIN_DIR:$PATH"

ADD docker/assets/* /
RUN chmod +x /entrypoint.sh

COPY --from=build /opt/venv /opt/venv

VOLUME [ "/app" ]
CMD [ "/bin/bash", "-c", "/entrypoint.sh" ]
