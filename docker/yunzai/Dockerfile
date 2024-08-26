FROM wyf7685/bot7685:yunzai-base

WORKDIR /app

COPY start.sh /
RUN git clone https://github.com/TimeRainStarSky/Yunzai /app \
    && git clone https://github.com/TomyJan/Yunzai-Kuro-Plugin.git /app/plugins/Yunzai-Kuro-Plugin \
    && cd /app && npm install pnpm -g && pnpm install -P \
    && chmod +x /start.sh \
    && rm -rf /app/plugins/example /app/plugins/other /app/plugins/system

VOLUME [ "/app/config", "/app/data", "/app/logs" ]
VOLUME [ "/app/plugins/Yunzai-Kuro-Plugin/config", "/app/plugins/Yunzai-Kuro-Plugin/data" ]

CMD ["/start.sh"]
