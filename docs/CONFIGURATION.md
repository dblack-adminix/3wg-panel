# Configuration Reference

3WG Panel is configured through `.env`.

## Core Variables

| Variable | Example | Description |
| --- | --- | --- |
| `PANEL_USER` | `admin` | Web login username |
| `PANEL_PASSWORD` | `change-me` | Web login password |
| `SESSION_SECRET` | random hex | Secret used to sign session cookies |
| `ENDPOINT_HOST` | `vpn.example.com` | Host written into generated client configs |
| `DNS_SERVERS` | `1.1.1.1, 1.0.0.1` | DNS pushed into generated configs |
| `HIDE_EXISTING_PEERS` | `1` | Hide peers not created by 3WG Panel |

## WireGuard Variables

| Variable | Example | Description |
| --- | --- | --- |
| `WG_CONTAINER` | `amnezia-wireguard` | Docker container name |
| `WG_INTERFACE` | `wg0` | Interface name inside the container |
| `WG_PORT` | `51820` | Public UDP port |
| `WG_CONFIG_PATH` | `/opt/amnezia/wireguard/wg0.conf` | Config path inside the container |
| `WG_NETWORK` | `10.8.1.0/24` | Client address pool |

## AmneziaWG Variables

| Variable | Example | Description |
| --- | --- | --- |
| `AWG_CONTAINER` | `amnezia-awg2` | Docker container name |
| `AWG_INTERFACE` | `awg0` | Interface name inside the container |
| `AWG_PORT` | `42300` | Public UDP port |
| `AWG_CONFIG_PATH` | `/opt/amnezia/awg/awg0.conf` | Config path inside the container |
| `AWG_NETWORK` | `10.8.1.0/24` | Client address pool |

## Data Paths

Inside the container:

```text
/app/data      SQLite database
/app/clients   generated client configs
/app/backups   backups and deleted configs
```

On the host those paths are mounted from the installation directory, usually:

```text
/opt/3wg-panel/data
/opt/3wg-panel/clients
/opt/3wg-panel/backups
```

## Notes

- If both WireGuard and AmneziaWG use the same CIDR, make sure this matches your real network design.
- `ENDPOINT_HOST` should be the domain clients can reach from the Internet.
- Do not commit `.env` to Git.
