#!/usr/bin/env bash
set -euo pipefail

args="$*"
case "$args" in
  *"--yesno"*) exit 0 ;;
  *"--msgbox"*) exit 0 ;;
  *"--gauge"*) cat >/dev/null; exit 0 ;;
  *"--textbox"*) exit 0 ;;
  *"--menu Выберите продукт"*) printf 'core' >&2 ;;
  *"--menu VPN-контейнеры"*) printf 'create' >&2 ;;
  *"Публичный домен панели"*) printf 'vpn.example.com' >&2 ;;
  *"VPN endpoint"*) printf 'vpn.example.com' >&2 ;;
  *"Каталог установки"*) printf '%s' "${MOCK_INSTALL_DIR:-/tmp/3wg-tui-test}" >&2 ;;
  *"Локальный адрес панели"*) printf '127.0.0.1' >&2 ;;
  *"Локальный TCP-порт"*) printf '18080' >&2 ;;
  *"WireGuard UDP-порт"*) printf '51820' >&2 ;;
  *"AmneziaWG UDP-порт"*) printf '443' >&2 ;;
  *"WireGuard сеть CIDR"*) printf '10.49.0.0/24' >&2 ;;
  *"AmneziaWG сеть CIDR"*) printf '10.50.0.0/24' >&2 ;;
  *"DNS для VPN-клиентов"*) printf '1.1.1.1, 1.0.0.1' >&2 ;;
  *"Логин администратора"*) printf 'admin' >&2 ;;
  *"--passwordbox"*) printf '' >&2 ;;
  *) printf 'Unexpected whiptail call: %s\n' "$args" >&2; exit 1 ;;
esac
