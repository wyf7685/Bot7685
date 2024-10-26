FROM wyf7685/bot7685:yunzai-base

WORKDIR /app

COPY start.sh /

RUN git clone https://github.com/TimeRainStarSky/Yunzai /app && \
    git clone https://github.com/TomyJan/Yunzai-Kuro-Plugin.git /app/plugins/Yunzai-Kuro-Plugin && \
    pnpm install -P && \
    chmod +x /start.sh && \
    rm -rf /app/plugins/example /app/plugins/other /app/plugins/system /app/plugins/Yunzai-Kuro-Plugin/apps/toy.js && \
    chown ${UID}:${GID} /app && \
    chown -R ${UID}:${GID} /app/config && \
    chown -R ${UID}:${GID} /app/plugins/Yunzai-Kuro-Plugin/config && \
    chown -R ${UID}:${GID} /app/plugins/Yunzai-Kuro-Plugin/data

VOLUME [ "/app/config", "/app/data", "/app/logs" ]
VOLUME [ "/app/plugins/Yunzai-Kuro-Plugin/config", "/app/plugins/Yunzai-Kuro-Plugin/data" ]

CMD [ "/bin/bash", "-c", "/start.sh" ]
