FROM python:3.12.2 as wheels

WORKDIR /wheel

COPY ./requirements.txt /wheel/

RUN python -m pip wheel --wheel-dir=/wheel --no-cache-dir --requirement ./requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

FROM python:3.12.2-slim

WORKDIR /app

ENV TZ Asia/Shanghai
ENV PYTHONPATH=/app

COPY ./docker/gunicorn_conf.py ./docker/start.sh /
RUN chmod +x /start.sh

ENV APP_MODULE _main:app
ENV MAX_WORKERS 1

COPY --from=wheels /wheel /wheel

RUN pip install --no-cache-dir --no-index --force-reinstall --find-links=/wheel -r /wheel/requirements.txt && rm -rf /wheel
VOLUME [ "/app", "/root/.config/meme_generator" ]

COPY ./docker/fonts /usr/share/fonts/meme-fonts/
RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources \
  && apt-get update \
  && apt-get install -y --no-install-recommends locales fontconfig fonts-noto-color-emoji gettext \
  && localedef -i zh_CN -c -f UTF-8 -A /usr/share/locale/locale.alias zh_CN.UTF-8 \
  && fc-cache -fv \
  && apt-get purge -y --auto-remove \
  && rm -rf /var/lib/apt/lists/*

RUN /usr/local/bin/meme download && rm -rf /root/.config/meme_generator/

CMD ["/start.sh"]
