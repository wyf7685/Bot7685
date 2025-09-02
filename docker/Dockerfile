FROM buildpack-deps:bookworm AS silk

ADD https://github.com/kn007/silk-v3-decoder.git /data

RUN chmod +x /data/converter.sh && \
    /data/converter.sh && \
    mkdir -p /out/silk && \
    mv /data/converter.sh /out && \
    mv /data/silk/decoder /out/silk

FROM python:3.13-slim-bookworm AS venv

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git ca-certificates python3-dev gcc g++ build-essential \
        libffi-dev libssl-dev zlib1g-dev liblzma-dev libbz2-dev libreadline-dev \
        libfreetype6-dev pkg-config

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/
WORKDIR /app

RUN uv venv /opt/venv
ENV UV_LINK_MODE=copy
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=external,target=external,rw \
    uv sync --locked --active --no-dev

FROM python:3.13-slim-bookworm AS app

WORKDIR /app

ENV TZ=Asia/Shanghai \
    LANG=zh_CN.UTF-8 \
    LANGUAGE=zh_CN.UTF-8 \
    LC_ALL=zh_CN.UTF-8 \
    PYTHONPATH=/app \
    APP_MODULE=bot:app \
    MAX_WORKERS=1 \
    VIRTUAL_ENV=/opt/venv \
    UV_TOOL_BIN_DIR=/opt/uv-bin/

ADD docker/fonts/*.ttf /usr/share/fonts/
ADD docker/assets/* /

RUN apt-get update && apt-get install -y --no-install-recommends \ 
        nano ffmpeg fontconfig locales locales-all fonts-noto \
        libnss3-dev libxss1 libasound2 libxrandr2 libatk1.0-0 \
        libgtk-3-0 libgbm-dev libxshmfence1 && \
    fc-cache -f -v && \
    rm -rf /var/lib/apt/lists/* && \
    chmod +x /entrypoint.sh

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
RUN uvx --no-cache playwright@1.55.0 install chromium --with-deps && \
    rm -rf /var/lib/apt/lists/*

COPY --from=silk /out /opt/silk-decoder
COPY --from=venv /opt/venv /opt/venv

ENV PATH="$VIRTUAL_ENV/bin:$UV_TOOL_BIN_DIR:$PATH"
VOLUME [ "/app" ]
CMD [ "/bin/bash", "-c", "/entrypoint.sh" ]
