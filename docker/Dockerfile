FROM python:3.14-slim-bookworm AS venv

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    git ca-certificates

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,from=ghcr.io/astral-sh/uv:latest,source=/uv,target=/bin/uv \
    uv venv /opt/venv && \
    . /opt/venv/bin/activate && \
    uv sync --locked --active --no-dev --link-mode copy

FROM python:3.14-slim-bookworm AS app

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates nano \    
    libglib2.0-0 libsm6 libxext6 libxrender1 liburing2

WORKDIR /app

ENV TZ=Asia/Shanghai \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    HOST=0.0.0.0 \
    PORT=8080 \
    WEB_CONCURRENCY=1

COPY --from=venv /opt/venv /opt/venv

VOLUME [ "/app" ]
ENTRYPOINT [ "python3", "bot.py" ]
