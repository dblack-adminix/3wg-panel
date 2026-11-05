# Изолированный транспортный пилот РФ → Европа

## Вариант AmneziaWG

Проверенный пилот использует `Dockerfile.awg` и
`generate.py --engine amneziawg`. Для сборки нужен установленный образ
`3wg-amneziawg-runtime:local`; результат тегируется
`3wg-cascade-pilot:amneziawg`. На втором хосте можно загрузить тот же образ
через `docker save` / `docker load`. У контейнеров должен быть доступ к
`/dev/net/tun`. Общие параметры маскировки генерируются вместе с ключами.
Для проверки состояния вместо `wg show` используйте `awg show`.

```bash
docker build -t 3wg-cascade-pilot:amneziawg -f cascade-pilot/Dockerfile.awg .
python3 cascade-pilot/generate.py --engine amneziawg --exit-ip EUROPE_IPV4 --output /root/3wg-cascade-pilot-awg
```

## Границы пилота

Это проверка межсерверного транспорта, не готовый общий VPN-вход и не
автоматизация каскада из Control. Пользовательские пиры не переключаются.
Контейнеры имеют отдельные network namespace, без host networking и
доступа к Docker socket. Меняются только их внутренние маршруты и firewall.

Сборка на обоих хостах из корня репозитория:

```bash
docker build -t 3wg-cascade-pilot:local -f cascade-pilot/Dockerfile .
```

Генерация ключей требует локального образа `3wg-wireguard-runtime:local`.
Каталог назначения не должен существовать. Файлы с ключами не публикуйте.

```bash
python3 cascade-pilot/generate.py --exit-ip EUROPE_IPV4 --output /root/3wg-cascade-pilot
```

Перенесите только `entry/` на сервер РФ, `exit/` оставьте на европейском.
В соответствующем каталоге:

```bash
docker compose -f compose.json up -d
```

На европейском сервере должен быть свободен `54443/udp`. В пилоте
используются `10.254.203.0/30` (транспорт) и резерв `10.203.0.0/24`
(будущие тестовые клиенты). Проверьте отсутствие конфликтов до запуска.
На входном контейнере отсутствует интерфейс клиентского VPN.

Проверка со входного контейнера:

```bash
docker exec 3wg-cascade-pilot-entry ping -c 3 -I wg-cascade 10.254.203.2
docker exec 3wg-cascade-pilot-entry curl --interface wg-cascade --max-time 15 https://api.ipify.org
```

Для проверки отказа остановите выходной контейнер, повторите curl с
привязкой к интерфейсу и убедитесь, что он завершается по тайм-ауту, затем
запустите выход снова. Это проверка транспорта, а не всех сценариев
fail-closed будущих клиентов. При падении самого интерфейса отдельное
правило FORWARD не разрешает выход тестовых клиентов через eth0.

Откат: `docker compose -f compose.json down` на обоих серверах. Сохраните
конфигурации отдельно в защищённом резерве. Для production ещё нужны
общий VPN-вход, учёт принадлежности пиров, доменные политики и управление
жизненным циклом из Control.
