#!/usr/bin/env bash
#
# Ротация логов nginx, которые лежат на хосте — том ./logs/nginx.
#
# Зачем: внутри образа /var/log/nginx/access.log и error.log — симлинки на
# stdout/stderr, поэтому при пересоздании контейнера логи исчезают (деплой
# делает `up -d --force-recreate` при каждом пуше). Именно так пропали
# access-логи за 17.10.2026, когда их разбирали. Поэтому nginx пишет в каталог
# на хосте, а этот скрипт его подрезает, чтобы диск не кончился.
#
# Как: copytruncate — копия и усечение исходного файла. nginx держит файл
# открытым, но открывает его в режиме добавления, поэтому после усечения
# продолжает писать в тот же файл (проверено: «дырки» из нулевых байтов не
# появляется), а перезапускать nginx не нужно.
#
# Переменные:
#   LOG_DIR   каталог с логами  (по умолчанию ~/duty/logs/nginx)
#   KEEP_DAYS сколько дней хранить (по умолчанию 14)
#
# Ставится по cron скриптом install-backup-cron.sh.

set -euo pipefail

LOG_DIR="${LOG_DIR:-$HOME/duty/logs/nginx}"
KEEP_DAYS="${KEEP_DAYS:-14}"
STAMP="$(date +%Y%m%d-%H%M%S)"

if [ ! -d "$LOG_DIR" ]; then
    # Первый запуск может случиться раньше, чем nginx создаст каталог.
    echo "Логи nginx не найдены: нет каталога $LOG_DIR"
    exit 0
fi

rotated=0
for log in "$LOG_DIR"/*.log; do
    [ -f "$log" ] || continue          # каталог пуст — шаблон не раскрылся
    [ -s "$log" ] || continue          # пустой файл не трогаем
    cp "$log" "$log.$STAMP"
    : > "$log"
    gzip -f "$log.$STAMP"
    rotated=$((rotated + 1))
done

# Единственное место, где мы что-то удаляем: свои же архивы старше KEEP_DAYS.
find "$LOG_DIR" -maxdepth 1 -type f -name '*.gz' -mtime "+$KEEP_DAYS" -delete

echo "Ротация логов nginx: повёрнуто файлов — $rotated, храним $KEEP_DAYS дней ($LOG_DIR)"
