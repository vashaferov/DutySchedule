#!/usr/bin/env bash
#
# Проверка scripts/rotate-nginx-logs.sh.
#
# Логи nginx лежат на хосте и растут, пока их не подрежут. Проверяем главное:
#   * непустой лог копируется в архив и усекается (nginx продолжает писать в
#     тот же файл, перезапуск не нужен);
#   * пустые логи не превращаются в пустые архивы;
#   * удаляются только свои старые архивы, чужие файлы остаются.
#
# Запуск: bash tests/scripts/rotate-nginx-logs.test.sh

set -uo pipefail

BASH_BIN="$(command -v bash)"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
script="$here/scripts/rotate-nginx-logs.sh"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

logs="$work/logs"
export LOG_DIR="$logs"

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

# Число файлов, подходящих под шаблон (0, если совпадений нет).
count_glob() {
    ls $1 2>/dev/null | wc -l | tr -d ' '
}

echo "1. Ротация непустых логов, чужие файлы не трогаем"
mkdir -p "$logs"
printf 'первая строка\nвторая строка\n' > "$logs/access.log"
printf 'ошибка\n' > "$logs/error.log"
: > "$logs/empty.log"
printf 'не лог\n' > "$logs/notes.txt"

rc=0
"$BASH_BIN" "$script" > "$work/out1" 2>&1 || rc=$?
check "0" "$rc" "код возврата 0"
check "0" "$(wc -c < "$logs/access.log" | tr -d ' ')" "access.log усечён"
check "0" "$(wc -c < "$logs/error.log" | tr -d ' ')" "error.log усечён"
check "1" "$(count_glob "$logs/access.log.*.gz")" "для access.log создан один архив"
check "1" "$(count_glob "$logs/error.log.*.gz")" "для error.log создан один архив"
check "0" "$(count_glob "$logs/empty.log.*")" "пустой лог не архивируется"
check "1" "$(count_glob "$logs/notes.txt")" "посторонний файл остался на месте"
archive="$(ls $logs/access.log.*.gz 2>/dev/null | head -n1)"
check "2" "$(gzip -dc "$archive" | wc -l | tr -d ' ')" "в архиве обе строки"
check "1" "$(grep -c 'повёрнуто файлов — 2' "$work/out1")" "в выводе число повёрнутых файлов"

echo "2. Повторный прогон: пустые логи не плодят архивы"
rc=0
"$BASH_BIN" "$script" > "$work/out2" 2>&1 || rc=$?
check "0" "$rc" "код возврата 0"
check "1" "$(count_glob "$logs/access.log.*.gz")" "новых архивов не появилось"

echo "3. Старые архивы удаляются, свежие остаются"
# архивы из шагов 1–2 отодвигаем в прошлое, а сегодняшний создаём прогоном
for f in "$logs"/*.gz; do
    [ -f "$f" ] || continue
    touch -d "30 days ago" "$f"
done
printf 'сегодня\n' > "$logs/today.log"

rc=0
KEEP_DAYS=14 "$BASH_BIN" "$script" > "$work/out3" 2>&1 || rc=$?
check "0" "$rc" "код возврата 0"
check "0" "$(count_glob "$logs/access.log.*.gz")" "архивы старше 14 дней удалены"
check "1" "$(count_glob "$logs/today.log.*.gz")" "свежий архив остался"

echo "4. Каталога нет — предупреждение и код 0"
rc=0
LOG_DIR="$work/no-such-dir" "$BASH_BIN" "$script" > "$work/out5" 2>&1 || rc=$?
check "0" "$rc" "код возврата 0"
check "1" "$(grep -c 'не найдены' "$work/out5")" "предупреждение выведено"

echo
if [ "$failures" -eq 0 ]; then
    echo "Все проверки пройдены"
    exit 0
fi
echo "Провалено проверок: $failures"
exit 1
