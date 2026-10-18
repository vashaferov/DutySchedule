#!/usr/bin/env bash
#
# Ставит (или обновляет) ежедневный cron для scripts/backup-db.sh.
# Запускается деплоем на хосте: bash ~/duty/scripts/install-backup-cron.sh
#
# Отдельный файл, а не строки прямо в deploy.yml: appleboy/ssh-action со
# script_stop: true обрывает деплой на ЛЮБОМ ненулевом коде команды, включая
# проверки внутри условий, которые законно вернули 1 (grep без совпадений,
# crontab -l без таблицы). В обычном скрипте такого ограничения нет.
#
# Переменные:
#   BACKUP_DIR  каталог бэкапов и логов (по умолчанию ~/duty-backups)
#   CRON_HOUR   час запуска             (по умолчанию 3)
#   CRON_MINUTE минута запуска          (по умолчанию 15)
#   ENV_FILE    .env с DB_USER/DB_NAME  (по умолчанию ~/duty/.env)
#
# Скрипт не считает проблемой отсутствие crontab или самого бэкап-скрипта:
# он предупреждает и выходит с кодом 0, чтобы не ронять деплой. Реальные
# ошибки (crontab не принял таблицу) — ненулевой код.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_SCRIPT="$SCRIPT_DIR/backup-db.sh"
BACKUP_DIR="${BACKUP_DIR:-$HOME/duty-backups}"
ENV_FILE="${ENV_FILE:-$HOME/duty/.env}"
CRON_HOUR="${CRON_HOUR:-3}"
CRON_MINUTE="${CRON_MINUTE:-15}"
# Метка в конце строки cron: по ней находим и заменяем свою задачу,
# не трогая чужие.
MARKER="# duty-db-backup"

if [ ! -f "$BACKUP_SCRIPT" ]; then
    echo "⚠️  Бэкапы не настроены: не найден $BACKUP_SCRIPT — см. RUNBOOK.md"
    exit 0
fi

if ! command -v crontab >/dev/null 2>&1; then
    echo "⚠️  Бэкапы не настроены: нет crontab — см. RUNBOOK.md"
    exit 0
fi

chmod +x "$BACKUP_SCRIPT"
mkdir -p "$BACKUP_DIR"

cron_line="$CRON_MINUTE $CRON_HOUR * * * ENV_FILE=$ENV_FILE BACKUP_DIR=$BACKUP_DIR $BACKUP_SCRIPT >> $BACKUP_DIR/backup.log 2>&1 $MARKER"

tmp_table="$(mktemp)"
trap 'rm -f "$tmp_table"' EXIT

# Существующую таблицу сохраняем, свою строку выкидываем и дописываем свежую.
# crontab -l ругается, если таблицы ещё нет, а grep возвращает 1, когда
# выкинул все строки, — оба случая штатные.
crontab -l 2>/dev/null | grep -v -F "$MARKER" > "$tmp_table" || true
echo "$cron_line" >> "$tmp_table"

if ! crontab "$tmp_table"; then
    echo "❌ Не удалось установить crontab — бэкапы не настроены" >&2
    exit 1
fi

echo "✅ Бэкапы: ежедневно в $(printf '%02d:%02d' "$CRON_HOUR" "$CRON_MINUTE"), каталог $BACKUP_DIR, храним 14 дней"
