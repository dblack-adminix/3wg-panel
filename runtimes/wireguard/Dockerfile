FROM alpine:3.20

LABEL maintainer="3WG Panel"

RUN apk add --no-cache bash dumb-init iproute2 iptables wireguard-tools

RUN mkdir -p /opt/amnezia/wireguard

COPY start.sh /opt/3wg/start.sh
RUN chmod +x /opt/3wg/start.sh

ENTRYPOINT ["dumb-init", "/opt/3wg/start.sh"]
