FROM amneziavpn/amneziawg-go@sha256:cbafc02b8373a83f428272db6d8001b37bc02e6211cbd8c0cb4e2e3759b12b72
RUN apk add --no-cache bash dumb-init iproute2 iptables
COPY start.sh /opt/3wg-exit-start.sh
ENTRYPOINT ["dumb-init", "sh", "/opt/3wg-exit-start.sh"]
