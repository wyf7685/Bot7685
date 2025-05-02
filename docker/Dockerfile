FROM python:3.13-slim-bookworm AS build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/

RUN uv venv /opt/venv
ENV UV_LINK_MODE=copy
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git ca-certificates python3-dev gcc g++ build-essential \
        libffi-dev libssl-dev zlib1g-dev liblzma-dev libbz2-dev libreadline-dev \
        libfreetype6-dev pkg-config

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --active --no-dev

FROM wyf7685/bot7685:base AS app

WORKDIR /app

ADD docker/assets/* /
RUN chmod +x /entrypoint.sh

ENV PYTHONPATH=/app \
    APP_MODULE=bot:app \
    MAX_WORKERS=1 \
    VIRTUAL_ENV=/opt/venv \
    UV_LINK_MODE=copy \
    UV_TOOL_BIN_DIR=/opt/uv-bin/

ENV PATH="$VIRTUAL_ENV/bin:$UV_TOOL_BIN_DIR:$PATH"

COPY --from=build /opt/venv /opt/venv

VOLUME [ "/app" ]
CMD [ "/bin/bash", "-c", "/entrypoint.sh" ]
