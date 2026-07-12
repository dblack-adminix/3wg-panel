FROM amneziavpn/amneziawg-go:latest

LABEL maintainer="3WG Panel"

RUN apk add --no-cache bash curl dumb-init iproute2 iptables

RUN mkdir -p /opt/amnezia/awg

COPY start.sh /opt/3wg/start.sh
RUN chmod +x /opt/3wg/start.sh

ENTRYPOINT ["dumb-init", "/opt/3wg/start.sh"]
