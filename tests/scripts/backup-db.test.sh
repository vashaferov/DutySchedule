#!/usr/bin/env bash
#
# Проверка scripts/backup-db.sh.
#
# Зачем отдельный тест: скрипт запускается по cron и в деплое, а его ошибка
# видна только в backup.log. Так и вышло 22.10.2026: pg_dump -F c писал формат
# PGDMP без gzip, проверка `gzip -t` всегда падала, и бэкапов не было вообще,
# хотя деплой «успешно» ставил cron. Деплой поймал это только когда бэкап
# понадобился перед выкаткой.
#
# Тест подменяет docker: pg_dump отдаёт fake-дамп в формате PGDMP, pg_restore
# читает stdin. Всё остальное (gzip, mv, find, права) — настоящее.
#
# Запуск: bash tests/scripts/backup-db.test.sh

set -uo pipefail

BASH_BIN="$(command -v bash)"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
script="${BACKUP_SCRIPT:-$here/scripts/backup-db.sh}"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

failures=0
check() {
    # check <ожидаемое> <полученное> <описание>
    if [ "$1" = "$2" ]; then
        echo "  ok: $3"
    else
        echo "  FAIL: $3 — ожидалось [$1], получено [$2]"
        failures=$((failures + 1))
    fi
}

count_backups() {
    ls "$BACKUP_DIR"/duty-*.dump.gz 2>/dev/null | wc -l | tr -d ' '
}

mkdir -p "$work/bin" "$work/home"
printf 'DB_USER=duty\nDB_NAME=duty\n' > "$work/env"

# Заглушка docker. Важно: pg_dump отдаёт НЕ gzip (как настоящий -F c),
# а pg_restore проверяет, что до него дошёл уже распакованный PGDMP.
cat > "$work/bin/docker" <<'STUB'
#!/usr/bin/env bash
if [ "${1:-}" = "inspect" ]; then
    printf '%s\n' "${STUB_CONTAINER_RUNNING:-true}"
    exit 0
fi
for arg in "$@"; do
    if [ "$arg" = "pg_dump" ]; then
        if [ "${STUB_PGDUMP_FAIL:-0}" = "1" ]; then
            echo "pg_dump: simulated failure" >&2
            exit 1
        fi
        printf 'PGDMP fake custom format\n'
        exit 0
    fi
    if [ "$arg" = "pg_restore" ]; then
        input="$(cat)"
        if printf '%s' "$input" | grep -q 'PGDMP'; then
            echo "fake table"
            exit 0
        fi
        echo "pg_restore: input is not a PGDMP dump" >&2
        exit 1
    fi
done
exit 0
STUB
chmod +x "$work/bin/docker"

run_backup() {
    # run_backup [доп. переменные...] — печатает код возврата
    local rc=0
    env -u BACKUP_REMOTE \
        PATH="$work/bin:$PATH" \
        HOME="$work/home" \
        ENV_FILE="$work/env" \
        BACKUP_DIR="$BACKUP_DIR" \
        "$@" \
        "$BASH_BIN" "$script" > "$work/out" 2>&1 || rc=$?
    echo "$rc"
}

echo "1. Успешный бэкап: дамп сжат gzip и читается pg_restore"
BACKUP_DIR="$work/backups"
rm -rf "$BACKUP_DIR"
rc="$(run_backup)"
check "0" "$rc" "код возврата 0"
check "1" "$(count_backups)" "создан ровно один файл .dump.gz"
dump="$(ls "$BACKUP_DIR"/duty-*.dump.gz 2>/dev/null | head -n1)"
if [ -n "$dump" ] && gzip -t "$dump" 2>/dev/null; then
    echo "  ok: файл действительно gzip"
else
    echo "  FAIL: файл не проходит gzip -t (это и была ошибка 22.10.2026)"
    failures=$((failures + 1))
fi
if [ -n "$dump" ] && gzip -dc "$dump" 2>/dev/null | grep -q 'PGDMP'; then
    echo "  ok: внутри распакованного дампа формат PGDMP"
else
    echo "  FAIL: внутри дампа нет PGDMP"
    failures=$((failures + 1))
fi
check "600" "$(stat -c '%a' "$dump" 2>/dev/null)" "права на дамп 600"
check "0" "$(ls "$BACKUP_DIR"/*.part 2>/dev/null | wc -l | tr -d ' ')" "временный .part не остался"

echo "2. pg_dump упал: код 1, готового файла нет"
BACKUP_DIR="$work/backups-fail"
rm -rf "$BACKUP_DIR"
rc="$(run_backup STUB_PGDUMP_FAIL=1)"
check "1" "$rc" "код возврата 1"
check "0" "$(count_backups)" "файл не создан"
check "0" "$(ls "$BACKUP_DIR"/*.part 2>/dev/null | wc -l | tr -d ' ')" "временный .part удалён"

echo "3. Контейнер не запущен: понятная ошибка, код 1"
BACKUP_DIR="$work/backups-stopped"
rc="$(run_backup STUB_CONTAINER_RUNNING=false)"
check "1" "$rc" "код возврата 1"
if grep -q 'не запущен' "$work/out"; then
    echo "  ok: сообщение про контейнер"
else
    echo "  FAIL: нет сообщения «не запущен»"
    failures=$((failures + 1))
fi

echo "4. Ротация: старый дамп удаляется, свежий остаётся"
BACKUP_DIR="$work/backups-rotate"
mkdir -p "$BACKUP_DIR"
printf 'x' | gzip > "$BACKUP_DIR/duty-20000101-000000.dump.gz"
touch -d "30 days ago" "$BACKUP_DIR/duty-20000101-000000.dump.gz"
rc="$(run_backup)"
check "0" "$rc" "код возврата 0"
check "1" "$(count_backups)" "старый дамп удалён, новый остался"

echo
if [ "$failures" -eq 0 ]; then
    echo "Все проверки пройдены"
    exit 0
fi
echo "Провалено проверок: $failures"
exit 1
