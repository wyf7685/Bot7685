FROM buildpack-deps:bookworm AS silk

ADD https://github.com/kn007/silk-v3-decoder.git /data

RUN chmod +x /data/converter.sh && \
    /data/converter.sh && \
    mkdir -p /out/silk && \
    mv /data/converter.sh /out && \
    mv /data/silk/decoder /out/silk

FROM debian:bookworm-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    nano \
    ffmpeg \
    fontconfig \
    locales \
    fonts-noto && \
    echo "zh_CN.UTF-8 UTF-8" > /etc/locale.gen && \
    echo "en_US.UTF-8 UTF-8" >> /etc/locale.gen && \
    locale-gen && \
    rm -rf /var/lib/apt/lists/*

FROM base AS app

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

COPY docker/assets/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

COPY --from=silk /out /opt/silk-decoder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
RUN uv python install 3.14 --no-cache

VOLUME [ "/app", "/opt/venv", "/opt/uv-cache" ]
CMD [ "/bin/sh", "-c", "/entrypoint.sh" ]
