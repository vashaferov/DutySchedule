#!/usr/bin/env bash
#
# Проверка scripts/rollback.sh — путь отката, которым пользуются, когда деплой
# уже сломал сайт. Ошибка в этом скрипте обнаруживается в худший момент, поэтому
# проверяем его отдельно, с заглушкой вместо docker и настоящим git-репозиторием.
#
# Что важно проверить:
#   * reset --hard действительно возвращает код к тегу;
#   * контейнеры пересоздаются и /api/health дожидается;
#   * скрипт дорабатывает до конца, даже если reset --hard удалил его самого
#     (он копирует себя в /tmp — иначе bash читал бы несуществующий файл);
#   * без аргумента и с неизвестным тегом — понятные коды возврата.
#
# Запуск: bash tests/scripts/rollback.test.sh

set -uo pipefail

BASH_BIN="$(command -v bash)"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
script="$here/scripts/rollback.sh"

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

contains() {
    # contains <файл> <текст> <описание>
    if grep -qF -- "$2" "$1"; then
        echo "  ok: $3"
    else
        echo "  FAIL: $3 — нет [$2]"
        failures=$((failures + 1))
    fi
}

if [ ! -f "$script" ]; then
    echo "❌ Не найден $script"
    exit 1
fi

# --- Стенд: репозиторий из двух версий и заглушка docker-compose ----------
repo="$work/repo"
mkdir -p "$repo/scripts" "$work/bin"

(
    cd "$repo" || exit 1
    git init -q
    git config user.email "test@example.invalid"
    git config user.name "rollback test"

    # Версия 1 — «рабочая», на неё будем откатываться. Скрипта отката в ней нет:
    # так проверяется, что reset --hard может удалить скрипт прямо во время работы.
    echo "good" > version.txt
    git add -A
    git commit -qm "рабочая версия"
    git tag rollback-test

    # Версия 2 — «сломанная», уже со скриптом отката.
    echo "bad" > version.txt
    cp "$script" scripts/rollback.sh
    git add -A
    git commit -qm "сломанная версия"
)

cat > "$work/bin/docker-compose" <<'STUB'
#!/usr/bin/env bash
printf 'docker-compose %s\n' "$*" >> "$STUB_LOG"
exit 0
STUB
chmod +x "$work/bin/docker-compose"

export PATH="$work/bin:$PATH"
export COMPOSE_DIR="$repo"
export HOME="$work"
export STUB_LOG="$work/docker.log"

echo "1. Откат на тег возвращает код и пересобирает контейнеры"
out="$(STUB_LOG="$STUB_LOG" "$BASH_BIN" "$script" rollback-test 2>&1)"
rc=$?
check "0" "$rc" "код возврата 0"
check "$(git -C "$repo" rev-parse --short rollback-test)" \
      "$(git -C "$repo" rev-parse --short HEAD)" "HEAD стоит на теге"
check "good" "$(cat "$repo/version.txt")" "файлы вернулись к версии из тега"
contains "$work/docker.log" "up -d --force-recreate --build --remove-orphans" "контейнеры пересозданы"
contains "$work/docker.log" "exec -T api python" "ждали /api/health"
case "$out" in
    *"Откат выполнен"*) echo "  ok: сообщение об успехе" ;;
    *) echo "  FAIL: нет сообщения об успехе"; failures=$((failures + 1)) ;;
esac
if [ -f "$repo/scripts/rollback.sh" ]; then
    echo "  FAIL: скрипт не был удалён откатом — проверка self-copy ничего не проверяет"
    failures=$((failures + 1))
else
    echo "  ok: скрипт удалён откатом, но доработал (копия в /tmp)"
fi

echo "2. Понятные ошибки: без аргумента и с неизвестным тегом"
cp "$script" "$work/rollback.sh"
rc=0
"$BASH_BIN" "$work/rollback.sh" >/dev/null 2>&1 || rc=$?
check "2" "$rc" "без аргумента — код 2"

rc=0
"$BASH_BIN" "$work/rollback.sh" no-such-tag >/dev/null 2>&1 || rc=$?
check "1" "$rc" "неизвестная цель — код 1"

echo "3. Откат не трогает неотслеживаемые .env и logs/"
(
    cd "$repo" || exit 1
    echo "SECRET=keep" > .env
    mkdir -p logs
    echo "log" > logs/access.log
)
STUB_LOG="$work/docker.log" "$BASH_BIN" "$script" rollback-test >/dev/null 2>&1 || true
check "SECRET=keep" "$(cat "$repo/.env")" ".env остался"
check "log" "$(cat "$repo/logs/access.log")" "logs/ остались"

echo
if [ "$failures" -eq 0 ]; then
    echo "Все проверки пройдены"
    exit 0
fi
echo "Провалено проверок: $failures"
exit 1
