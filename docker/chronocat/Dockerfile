FROM wyf7685/bot7685:chronocat-base

ENV DEBIAN_FRONTEND=noninteractive
ENV VNC_PASSWD=vncpasswd

RUN git config --global http.sslVerify false && git config --global http.postBuffer 1048576000 \
    && cd /opt && git clone https://github.com/novnc/noVNC.git \
    && cd /opt/noVNC/utils && git clone https://github.com/novnc/websockify.git \
    && cp /opt/noVNC/vnc.html /opt/noVNC/index.html

RUN curl -o /root/linuxqq.deb https://dldir1.qq.com/qqfile/qq/QQNT/f60e8252/linuxqq_3.2.12-28327_amd64.deb \
    && dpkg -i /root/linuxqq.deb \
    && apt-get -f install -y \
    && rm /root/linuxqq.deb

RUN curl -L -o /tmp/LiteLoaderQQNT.zip https://github.com/LiteLoaderQQNT/LiteLoaderQQNT/releases/download/1.2.2/LiteLoaderQQNT.zip \
    && unzip /tmp/LiteLoaderQQNT.zip -d /opt/QQ/resources/app/LiteLoader/ \
    && mkdir -p /opt/QQ/resources/app/LiteLoader/plugins \
    && rm /tmp/LiteLoaderQQNT.zip \
    && echo 'require("/opt/QQ/resources/app/LiteLoader");' > /opt/QQ/resources/app/app_launcher/llqqnt.js \
    && sed -i 's|"main": "[^"]*"|"main": "./app_launcher/llqqnt.js"|' /opt/QQ/resources/app/package.json

RUN curl -L -o /tmp/chronocat.zip https://github.com/chrononeko/chronocat/releases/download/v0.2.19/chronocat-llqqnt-v0.2.19.zip \
    && unzip /tmp/chronocat.zip -d /opt/QQ/resources/app/LiteLoader/plugins/ \
    && rm /tmp/chronocat.zip \
    && curl -L -o /tmp/chronocat.zip https://github.com/chrononeko/chronocat/releases/download/v0.2.19/chronocat-llqqnt-engine-chronocat-api-v0.2.19.zip \
    && unzip /tmp/chronocat.zip -d /opt/QQ/resources/app/LiteLoader/plugins/ \
    && rm /tmp/chronocat.zip \
    && curl -L -o /tmp/chronocat.zip https://github.com/chrononeko/chronocat/releases/download/v0.2.19/chronocat-llqqnt-engine-chronocat-event-v0.2.19.zip \
    && unzip /tmp/chronocat.zip -d /opt/QQ/resources/app/LiteLoader/plugins/ \
    && rm /tmp/chronocat.zip \
    && curl -L -o /tmp/chronocat.zip https://github.com/chrononeko/chronocat/releases/download/v0.2.19/chronocat-llqqnt-engine-crychiccat-v0.2.19.zip \
    && unzip /tmp/chronocat.zip -d /opt/QQ/resources/app/LiteLoader/plugins/ \
    && rm /tmp/chronocat.zip \
    && curl -L -o /tmp/chronocat.zip https://github.com/chrononeko/chronocat/releases/download/v0.2.19/chronocat-llqqnt-engine-media-v0.2.19.zip \
    && unzip /tmp/chronocat.zip -d /opt/QQ/resources/app/LiteLoader/plugins/ \
    && rm /tmp/chronocat.zip

RUN mkdir -p ~/.vnc \
    && echo "#!/bin/bash" > ~/start.sh \
    && echo "rm /tmp/.X1-lock" >> ~/start.sh \
    && echo "Xvfb :1 -screen 0 1280x1024x16 &" >> ~/start.sh \
    && echo "export DISPLAY=:1" >> ~/start.sh \
    && echo "fluxbox &" >> ~/start.sh \
    && echo "x11vnc -display :1 -noxrecord -noxfixes -noxdamage -forever -rfbauth ~/.vnc/passwd &" >> ~/start.sh \
    && echo "nohup /opt/noVNC/utils/novnc_proxy --vnc localhost:5900 --listen 6081 --file-only &" >> ~/start.sh \
    && echo "x11vnc -storepasswd \$VNC_PASSWD ~/.vnc/passwd" >> ~/start.sh \
    && echo "su -c 'qq --no-sandbox' root" >> ~/start.sh \
    && chmod +x ~/start.sh \
    && echo "[supervisord]" > /etc/supervisor/supervisord.conf \
    && echo "nodaemon=true" >> /etc/supervisor/supervisord.conf \
    && echo "[program:x11vnc]" >> /etc/supervisor/supervisord.conf \
    && echo "command=/usr/bin/x11vnc -display :1 -noxrecord -noxfixes -noxdamage -forever -rfbauth ~/.vnc/passwd" >> /etc/supervisor/supervisord.conf

CMD [ "/bin/bash", "-c", "/root/start.sh" ]
