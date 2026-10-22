#!/usr/bin/env bash
#
# Ставит (или обновляет) ежедневные служебные задачи на хосте:
#   * cron для scripts/backup-db.sh         — бэкап БД;
#   * cron для scripts/rotate-nginx-logs.sh — ротация логов nginx.
#
# Запускается деплоем на хосте: bash ~/duty/scripts/install-backup-cron.sh
#
# Отдельный файл, а не строки прямо в deploy.yml: appleboy/ssh-action со
# script_stop: true обрывает деплой на ЛЮБОМ ненулевом коде команды, включая
# проверки внутри условий, которые законно вернули 1 (grep без совпадений,
# crontab -l без таблицы). В обычном скрипте такого ограничения нет.
#
# Переменные:
#   BACKUP_DIR  каталог бэкапов и логов задач (по умолчанию ~/duty-backups)
#   LOG_DIR     каталог логов nginx            (по умолчанию ~/duty/logs/nginx)
#   KEEP_DAYS   сколько дней хранить логи      (по умолчанию 14)
#   CRON_HOUR   час запуска                    (по умолчанию 3)
#   CRON_MINUTE минута запуска                 (по умолчанию 15)
#   ENV_FILE    .env с DB_USER/DB_NAME         (по умолчанию ~/duty/.env)
#
# Скрипт не считает проблемой отсутствие crontab или самих задач: он
# предупреждает и выходит с кодом 0, чтобы не ронять деплой. Реальные ошибки
# (crontab не принял таблицу) — ненулевой код.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_SCRIPT="$SCRIPT_DIR/backup-db.sh"
ROTATE_SCRIPT="$SCRIPT_DIR/rotate-nginx-logs.sh"
BACKUP_DIR="${BACKUP_DIR:-$HOME/duty-backups}"
LOG_DIR="${LOG_DIR:-$HOME/duty/logs/nginx}"
KEEP_DAYS="${KEEP_DAYS:-14}"
ENV_FILE="${ENV_FILE:-$HOME/duty/.env}"
CRON_HOUR="${CRON_HOUR:-3}"
CRON_MINUTE="${CRON_MINUTE:-15}"
# Метки в конце строк cron: по ним находим и заменяем свои задачи,
# не трогая чужие.
BACKUP_MARKER="# duty-db-backup"
ROTATE_MARKER="# duty-nginx-logs"

if ! command -v crontab >/dev/null 2>&1; then
    echo "⚠️  Служебные задачи не настроены: нет crontab — см. RUNBOOK.md"
    exit 0
fi

mkdir -p "$BACKUP_DIR"

tmp_table="$(mktemp)"
trap 'rm -f "$tmp_table"' EXIT

# Существующую таблицу сохраняем, свои строки выкидываем и дописываем свежие.
# crontab -l ругается, если таблицы ещё нет, а grep возвращает 1, когда
# выкинул все строки, — оба случая штатные.
crontab -l 2>/dev/null | grep -v -F "$BACKUP_MARKER" | grep -v -F "$ROTATE_MARKER" > "$tmp_table" || true

added=0

if [ -f "$BACKUP_SCRIPT" ]; then
    chmod +x "$BACKUP_SCRIPT"
    echo "$CRON_MINUTE $CRON_HOUR * * * ENV_FILE=$ENV_FILE BACKUP_DIR=$BACKUP_DIR $BACKUP_SCRIPT >> $BACKUP_DIR/backup.log 2>&1 $BACKUP_MARKER" >> "$tmp_table"
    added=$((added + 1))
fi

if [ -f "$ROTATE_SCRIPT" ]; then
    chmod +x "$ROTATE_SCRIPT"
    echo "$CRON_MINUTE $CRON_HOUR * * * LOG_DIR=$LOG_DIR KEEP_DAYS=$KEEP_DAYS $ROTATE_SCRIPT >> $BACKUP_DIR/rotate-logs.log 2>&1 $ROTATE_MARKER" >> "$tmp_table"
    added=$((added + 1))
fi

if [ "$added" = "0" ]; then
    echo "⚠️  Служебные задачи не настроены: в $SCRIPT_DIR нет ни backup-db.sh, ни rotate-nginx-logs.sh — см. RUNBOOK.md"
    exit 0
fi

if ! crontab "$tmp_table"; then
    echo "❌ Не удалось установить crontab — служебные задачи не настроены" >&2
    exit 1
fi

echo "✅ Служебные задачи: ежедневно в $(printf '%02d:%02d' "$CRON_HOUR" "$CRON_MINUTE") — бэкап БД в $BACKUP_DIR и ротация логов nginx в $LOG_DIR (храним $KEEP_DAYS дней)"
