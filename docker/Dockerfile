FROM python:3.14-slim-bookworm AS venv

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    git ca-certificates
    # python3-dev gcc g++ build-essential \
    # libffi-dev libssl-dev zlib1g-dev liblzma-dev libbz2-dev libreadline-dev \
    # libfreetype6-dev pkg-config

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
    ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV TZ=Asia/Shanghai \
    LANG=zh_CN.UTF-8 \
    LANGUAGE=zh_CN:en_US \
    PYTHONPATH=/app \
    VIRTUAL_ENV=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

COPY docker/assets/* /
RUN chmod +x /entrypoint.sh

COPY --from=venv /opt/venv /opt/venv

VOLUME [ "/app" ]
CMD [ "/bin/sh", "-c", "/entrypoint.sh" ]
