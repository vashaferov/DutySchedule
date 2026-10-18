#!/usr/bin/env bash
#
# Проверка scripts/install-backup-cron.sh.
#
# Реальный crontab не трогаем: в PATH подкладываем заглушку, которая держит
# таблицу в файле. Проверяем главное, что может сломаться незаметно:
#   * задача вообще ставится (в том числе на пустой таблице, где crontab -l
#     возвращает ошибку — раньше именно такие проверки роняли деплой);
#   * повторный запуск обновляет свою строку, а не плодит дубликаты;
#   * чужие задачи пользователя остаются на месте;
#   * без crontab скрипт предупреждает и не валит деплой.
#
# Запуск: bash tests/scripts/install-backup-cron.test.sh

set -uo pipefail

BASH_BIN="$(command -v bash)"

here="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

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

# Число строк с совпадением. grep -c печатает 0 и возвращает 1, если совпадений
# нет, поэтому пропускаем вывод через head (не роняя проверку).
count_in_file() {
    grep -c -- "$1" "$2" 2>/dev/null | head -n1
}

# --- заглушка crontab ------------------------------------------------------
# -l печатает таблицу (ошибка, если таблицы нет — как у настоящего);
# crontab <файл> — сохраняет таблицу.
cat > "$work/crontab" <<'STUB'
#!/usr/bin/env bash
table="${FAKE_CRONTAB_TABLE:?}"
if [ "${1:-}" = "-l" ]; then
    [ -f "$table" ] || exit 1
    cat "$table"
    exit 0
fi
[ -n "${1:-}" ] || exit 2
cp "$1" "$table"
STUB
chmod +x "$work/crontab"

export FAKE_CRONTAB_TABLE="$work/table"
export HOME="$work/home"
mkdir -p "$HOME/duty/scripts" "$HOME/duty-backups"
cp "$here/scripts/install-backup-cron.sh" "$HOME/duty/scripts/"
cp "$here/scripts/backup-db.sh" "$HOME/duty/scripts/"

install_script="$HOME/duty/scripts/install-backup-cron.sh"

echo "1. Пустая таблица (crontab -l возвращает ошибку)"
rc=0
PATH="$work:$PATH" "$BASH_BIN" "$install_script" > "$work/out1" 2>&1 || rc=$?
check "0" "$rc" "код возврата 0"
check "1" "$(count_in_file 'duty-db-backup' "$FAKE_CRONTAB_TABLE")" "задача добавлена ровно один раз"
check "1" "$(count_in_file '^15 3 \* \* \*' "$FAKE_CRONTAB_TABLE")" "расписание 03:15"
check "1" "$(count_in_file 'backup-db.sh' "$FAKE_CRONTAB_TABLE")" "вызывается backup-db.sh"

echo "2. Повторный запуск: чужая задача цела, дубликата нет"
echo '0 5 * * * /usr/bin/other-job' >> "$FAKE_CRONTAB_TABLE"
rc=0
PATH="$work:$PATH" "$BASH_BIN" "$install_script" > "$work/out2" 2>&1 || rc=$?
check "0" "$rc" "код возврата 0"
check "1" "$(count_in_file 'duty-db-backup' "$FAKE_CRONTAB_TABLE")" "дубликат не появился"
check "1" "$(count_in_file 'other-job' "$FAKE_CRONTAB_TABLE")" "чужая задача сохранилась"
check "2" "$(wc -l < "$FAKE_CRONTAB_TABLE" | tr -d ' ')" "в таблице ровно 2 задачи"

echo "3. Нет crontab — только предупреждение, деплой не роняем"
# PATH без crontab, но с dirname: скрипт должен дойти до проверки crontab.
mkdir -p "$work/no-crontab"
cp "$(command -v dirname)" "$work/no-crontab/dirname"
rc=0
PATH="$work/no-crontab" "$BASH_BIN" "$install_script" > "$work/out3" 2>&1 || rc=$?
check "0" "$rc" "код возврата 0"
check "1" "$(count_in_file 'Бэкапы не настроены' "$work/out3")" "предупреждение выведено"

echo "4. Рядом нет backup-db.sh — тоже только предупреждение"
mv "$HOME/duty/scripts/backup-db.sh" "$work/backup-db.sh"
rc=0
PATH="$work:$PATH" "$BASH_BIN" "$install_script" > "$work/out4" 2>&1 || rc=$?
check "0" "$rc" "код возврата 0"
check "1" "$(count_in_file 'Бэкапы не настроены' "$work/out4")" "предупреждение выведено"
mv "$work/backup-db.sh" "$HOME/duty/scripts/backup-db.sh"

echo
if [ "$failures" -eq 0 ]; then
    echo "Все проверки пройдены"
    exit 0
fi
echo "Провалено проверок: $failures"
exit 1
