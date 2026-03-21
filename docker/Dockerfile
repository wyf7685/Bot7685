FROM debian:bookworm-slim AS venv

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    git ca-certificates python3-dev gcc g++ build-essential \
    libffi-dev libssl-dev zlib1g-dev liblzma-dev libbz2-dev libreadline-dev \
    libfreetype6-dev pkg-config

ENV UV_LINK_MODE=copy \
    UV_PYTHON_INSTALL_DIR=/opt/python
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
RUN uv python install 3.14 --no-cache

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /opt/venv && \
    . /opt/venv/bin/activate && \
    uv sync --locked --active --no-dev

FROM debian:bookworm-slim AS app

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates curl nano fontconfig locales fonts-noto && \
    echo "zh_CN.UTF-8 UTF-8" > /etc/locale.gen && \
    echo "en_US.UTF-8 UTF-8" >> /etc/locale.gen && \
    locale-gen

WORKDIR /app

ENV TZ=Asia/Shanghai \
    LANG=zh_CN.UTF-8 \
    LANGUAGE=zh_CN:en_US \
    PYTHONPATH=/app \
    VIRTUAL_ENV=/opt/venv \
    UV_PYTHON_INSTALL_DIR=/opt/python
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

COPY docker/assets/* /
RUN chmod +x /entrypoint.sh

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/
RUN uv python install 3.14 --no-cache

COPY --from=venv /opt/venv /opt/venv

VOLUME [ "/app" ]
CMD [ "/bin/sh", "-c", "/entrypoint.sh" ]
