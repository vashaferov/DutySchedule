#!/usr/bin/env bash
#
# Бэкап базы DutySchedule (pg_dump внутри контейнера duty_postgres).
# Запускается на ХОСТЕ (по cron), нужны только docker и gzip.
#
#   ENV_FILE=~/duty/.env ./scripts/backup-db.sh
#
# Переменные:
#   DB_CONTAINER   имя контейнера Postgres           (по умолчанию duty_postgres)
#   BACKUP_DIR     куда складывать дампы             (по умолчанию ~/duty-backups)
#   RETENTION_DAYS сколько дней хранить              (по умолчанию 14)
#   ENV_FILE       откуда взять DB_USER/DB_NAME      (по умолчанию ~/duty/.env)
#   BACKUP_REMOTE  опциональная команда копирования дампа наружу.
#                  Путь к свежему дампу доступен как $DUMP, например:
#                  BACKUP_REMOTE='rclone copy "$DUMP" remote:duty-backups'
#
# Всё пишется в stdout — cron отправит это письмом.

set -euo pipefail

# cron даёт урезанный PATH — стандартные каталоги иначе не найдутся.
# Текущий PATH оставляем первым: в тестах там заглушка docker, и она должна
# выигрывать у настоящего /usr/bin/docker (иначе тест ходит в реальный докер
# и падает на CI).
export PATH="${PATH:-}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

CONTAINER="${DB_CONTAINER:-duty_postgres}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/duty-backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
ENV_FILE="${ENV_FILE:-$HOME/duty/.env}"

log() { echo "$(date -Is) $*"; }

# Значение из .env достаём текстом, не выполняя файл: там лежит JSON/base64
# ключа Google Sheets, и `source` на нём легко ломается.
read_var() {
    [ -f "$1" ] || return 0
    sed -n "s/^[[:space:]]*$2[[:space:]]*=[[:space:]]*//p" "$1" | head -n1
}

DB_USER="${DB_USER:-$(read_var "$ENV_FILE" DB_USER)}"
DB_NAME="${DB_NAME:-$(read_var "$ENV_FILE" DB_NAME)}"

if [ -z "${DB_USER:-}" ] || [ -z "${DB_NAME:-}" ]; then
    log "ОШИБКА: не удалось определить DB_USER/DB_NAME (смотрел в $ENV_FILE)" >&2
    exit 1
fi

if [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null)" != "true" ]; then
    log "ОШИБКА: контейнер $CONTAINER не запущен" >&2
    exit 1
fi

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

timestamp="$(date -u +%Y%m%d-%H%M%S)"
final="$BACKUP_DIR/duty-$timestamp.dump.gz"
partial="$final.part"

cleanup() { rm -f "$partial"; }
trap cleanup EXIT

log "Дамп базы $DB_NAME из контейнера $CONTAINER..."
# -F c — custom format: восстанавливается pg_restore, можно смотреть содержимое.
# Сжимаем на хосте: pg_dump -F c отдаёт формат PGDMP (не gzip), а restore-db.sh
# и проверки ниже ожидают .dump.gz. Без `| gzip` gzip -t всегда падал — так
# ежедневные бэкапы не сохранялись вовсе. pipefail (см. set -euo) ловит ошибку
# любой из сторон конвейера.
if ! docker exec "$CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" -F c | gzip > "$partial"; then
    log "ОШИБКА: pg_dump или gzip завершились с ошибкой, бэкап не сохранён" >&2
    exit 1
fi

# Дамп пишем во временный файл и проверяем, что он читается целиком:
# битый бэкап хуже отсутствующего, потому что на него надеются.
if ! gzip -t "$partial" 2>/dev/null; then
    log "ОШИБКА: архив повреждён, бэкап не сохранён" >&2
    exit 1
fi

if ! gzip -dc "$partial" | docker exec -i "$CONTAINER" pg_restore --list > /dev/null; then
    log "ОШИБКА: pg_restore не смог прочитать дамп, бэкап не сохранён" >&2
    exit 1
fi

chmod 600 "$partial"
mv "$partial" "$final"
log "Готово: $final ($(du -h "$final" | cut -f1))"

# Ротация: старые дампы удаляем только после успешного нового.
find "$BACKUP_DIR" -maxdepth 1 -name 'duty-*.dump.gz' -type f -mtime "+$RETENTION_DAYS" -print -delete

# Копия за пределы сервера (если настроено). Без неё бэкап лежит на том же
# диске, что и база: смерть диска уносит оба.
if [ -n "${BACKUP_REMOTE:-}" ]; then
    log "Копирование наружу: $BACKUP_REMOTE"
    DUMP="$final"
    if eval "$BACKUP_REMOTE"; then
        log "Внешняя копия сделана"
    else
        log "ОШИБКА: внешнее копирование не удалось" >&2
        exit 1
    fi
fi
