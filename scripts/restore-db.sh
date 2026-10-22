#!/usr/bin/env bash
#
# Восстановление базы DutySchedule из дампа backup-db.sh.
#
#   ./scripts/restore-db.sh ~/duty-backups/duty-20261019-031500.dump.gz
#   ./scripts/restore-db.sh --yes <файл>     # без интерактивного подтверждения
#
# Дамп разворачивается с --clean --if-exists: объекты в целевой базе удаляются
# и создаются заново. Всё, что появилось в базе после снятия дампа, будет потеряно.
#
# Переменные: DB_CONTAINER, ENV_FILE (см. backup-db.sh), COMPOSE_DIR.

set -euo pipefail

# Стандартные каталоги в конец, текущий PATH — первым (см. backup-db.sh).
export PATH="${PATH:-}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

CONTAINER="${DB_CONTAINER:-duty_postgres}"
ENV_FILE="${ENV_FILE:-$HOME/duty/.env}"
COMPOSE_DIR="${COMPOSE_DIR:-$HOME/duty}"

ASSUME_YES=0
if [ "${1:-}" = "--yes" ]; then
    ASSUME_YES=1
    shift
fi

DUMP_FILE="${1:-}"
if [ -z "$DUMP_FILE" ]; then
    echo "Использование: $0 [--yes] <файл-дампа.dump.gz>" >&2
    exit 2
fi
if [ ! -f "$DUMP_FILE" ]; then
    echo "ОШИБКА: файл не найден: $DUMP_FILE" >&2
    exit 1
fi

log() { echo "$(date -Is) $*"; }

read_var() {
    [ -f "$1" ] || return 0
    sed -n "s/^[[:space:]]*$2[[:space:]]*=[[:space:]]*//p" "$1" | head -n1
}

DB_USER="${DB_USER:-$(read_var "$ENV_FILE" DB_USER)}"
DB_NAME="${DB_NAME:-$(read_var "$ENV_FILE" DB_NAME)}"
if [ -z "${DB_USER:-}" ] || [ -z "${DB_NAME:-}" ]; then
    echo "ОШИБКА: не удалось определить DB_USER/DB_NAME (смотрел в $ENV_FILE)" >&2
    exit 1
fi

if [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null)" != "true" ]; then
    echo "ОШИБКА: контейнер $CONTAINER не запущен" >&2
    exit 1
fi

if ! gzip -dc "$DUMP_FILE" | docker exec -i "$CONTAINER" pg_restore --list > /dev/null; then
    echo "ОШИБКА: дамп нечитаемый, восстановление отменено" >&2
    exit 1
fi

echo "Дамп:     $DUMP_FILE"
echo "База:     $DB_NAME в контейнере $CONTAINER"
echo "ВНИМАНИЕ: текущее содержимое базы будет перезаписано."
if [ "$ASSUME_YES" != "1" ]; then
    read -r -p "Напишите YES для продолжения: " answer
    if [ "$answer" != "YES" ]; then
        echo "Отменено."
        exit 1
    fi
fi

# Останавливаем писателей, чтобы в базу никто не писал во время восстановления.
compose() {
    if command -v docker-compose &>/dev/null; then
        (cd "$COMPOSE_DIR" && docker-compose "$@")
    else
        (cd "$COMPOSE_DIR" && docker compose "$@")
    fi
}

log "Останавливаю api и sync..."
compose stop api sync

log "Восстанавливаю из дампа..."
gzip -dc "$DUMP_FILE" | docker exec -i "$CONTAINER" \
    pg_restore -U "$DB_USER" -d "$DB_NAME" --clean --if-exists --no-owner

log "Поднимаю api и sync..."
compose start api sync

log "Готово. Проверьте приложение и синхронизацию с Google Sheets."
