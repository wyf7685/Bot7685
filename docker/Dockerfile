FROM debian:bookworm AS silk

ADD https://github.com/kn007/silk-v3-decoder.git /data

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ build-essential ffmpeg && \
    chmod +x /data/converter.sh && \
    /data/converter.sh && \
    mkdir -p /out/silk && \
    mv /data/converter.sh /out && \
    mv /data/silk/decoder /out/silk

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS venv

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

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS app

WORKDIR /app

ENV TZ=Asia/Shanghai \
    LANG=zh_CN.UTF-8 \
    LANGUAGE=zh_CN.UTF-8 \
    LC_ALL=zh_CN.UTF-8

ADD docker/fonts/*.ttf /usr/share/fonts/
ADD docker/assets/* /

RUN apt-get update && \
    apt-get install -y --no-install-recommends nano ffmpeg fontconfig \
    locales locales-all fonts-noto libnss3-dev libxss1 libasound2 libxrandr2 libatk1.0-0 libgtk-3-0 libgbm-dev libxshmfence1 && \
    fc-cache -f -v && \
    uvx --no-cache playwright@1.52.0 install chromium --with-deps && \
    apt-get purge -y --auto-remove && \
    chmod +x /entrypoint.sh

ENV PYTHONPATH=/app \
    APP_MODULE=bot:app \
    MAX_WORKERS=1 \
    VIRTUAL_ENV=/opt/venv \
    UV_LINK_MODE=copy \
    UV_TOOL_BIN_DIR=/opt/uv-bin/
ENV PATH="$VIRTUAL_ENV/bin:$UV_TOOL_BIN_DIR:$PATH"

COPY --from=silk /out /opt/silk-decoder
COPY --from=venv /opt/venv /opt/venv

VOLUME [ "/app" ]
CMD [ "/bin/bash", "-c", "/entrypoint.sh" ]
