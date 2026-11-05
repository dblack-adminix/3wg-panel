FROM alpine:3.20
RUN apk add --no-cache bash dumb-init iproute2 iptables wireguard-tools curl
COPY cascade-pilot/start.sh /opt/3wg/pilot.sh
ENTRYPOINT ["dumb-init", "bash", "/opt/3wg/pilot.sh"]
