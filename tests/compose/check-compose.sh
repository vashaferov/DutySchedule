#!/usr/bin/env bash
#
# Проверка docker-compose.yml.
#
# Ошибка в этом файле ломает не отдельную ручку, а весь деплой: `docker compose
# up` не поднимает ничего. Поэтому проверяем настоящим docker compose, что файл
# разбирается, и что в нём есть вещи, которые легко забыть, добавив новый сервис:
#
#   * healthcheck у postgres/api/sync/nginx — иначе Docker не знает, жив ли
#     сервис, и ни деплой, ни аптайм-чек этого не заметят;
#   * ограничение логов у каждого сервиса — иначе логи занимают весь диск;
#   * каталог логов nginx смонтирован на хост — иначе логи исчезают при
#     пересоздании контейнера (так пропали логи за 17.10.2026).
#
# Запуск: bash tests/compose/check-compose.sh

set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
compose_file="$here/docker-compose.yml"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

if ! command -v docker >/dev/null 2>&1; then
    echo "❌ Нет docker — проверить docker-compose.yml нечем"
    exit 1
fi

# .env в CI нет: compose предупредит о незаполненных переменных, но конфиг
# соберёт. Это ожидаемо и на результат не влияет.
#
# --profile tools: migrate живёт в профиле и по умолчанию в разбор не попадает,
# а проверить нужно и его.
if ! docker compose --profile tools -f "$compose_file" config --format json > "$work/config.json" 2> "$work/config.err"; then
    echo "❌ docker compose не разобрал $compose_file:"
    sed 's/^/    /' "$work/config.err" | head -20
    exit 1
fi
echo "  ok: docker-compose.yml разбирается"

python3 - "$work/config.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    config = json.load(fh)

failures = 0


def check(condition, message):
    global failures
    if condition:
        print(f"  ok: {message}")
    else:
        print(f"  FAIL: {message}")
        failures += 1


services = config.get("services", {})

# Живость: эти сервисы должны сообщать Docker, что они работают.
for name in ("postgres", "api", "sync", "nginx"):
    service = services.get(name)
    check(service is not None, f"сервис {name} есть в compose")
    if service is None:
        continue
    check("healthcheck" in service, f"у {name} есть healthcheck")

# migrate запускается руками, healthcheck ему не нужен.
check("migrate" in services, "сервис migrate есть в compose")
check(
    "healthcheck" not in services.get("migrate", {}),
    "у migrate healthcheck не нужен (запускается вручную)",
)

# Логи ограничены у всех: иначе один зациклившийся сервис занимает диск.
for name, service in sorted(services.items()):
    options = (service.get("logging") or {}).get("options") or {}
    check(
        options.get("max-size") == "10m" and str(options.get("max-file")) == "3",
        f"у {name} ограничен размер логов (10m, 3 файла)",
    )

# Логи nginx должны переживать пересоздание контейнера.
volumes = services.get("nginx", {}).get("volumes") or []
targets = [item.get("target") for item in volumes if isinstance(item, dict)]
check("/var/log/nginx" in targets, "логи nginx смонтированы на хост (/var/log/nginx)")

sys.exit(1 if failures else 0)
PY
rc=$?

if [ "$rc" -eq 0 ]; then
    echo "✅ docker-compose.yml: healthcheck-и и ограничения логов на месте"
else
    echo "❌ docker-compose.yml: проверки не пройдены"
fi
exit "$rc"
