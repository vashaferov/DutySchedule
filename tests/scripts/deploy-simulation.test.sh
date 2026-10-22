#!/usr/bin/env bash
#
# Прогоняет скрипт деплоя из deploy.yml ровно так, как его выполняет
# appleboy/ssh-action, — но с заглушками вместо git/docker/postgres.
#
# Зачем. При script_stop: true (а у нас именно так) ssh-action режет скрипт на
# строки и после каждой вставляет проверку кода возврата:
#
#     DRONE_SSH_PREV_COMMAND_EXIT_CODE=$? ; if [ $... -ne 0 ]; then exit $...; fi;
#
# Это не косметика: вставка идёт первой строкой каждой ветки, поэтому ветка
# else ВСЕГДА обрывает деплой — проверка видит код 1 от ложного условия.
# Именно так упал деплой 85de881 (а деплой a7b6b9c не запустился вовсе из-за
# case, который эта же вставка ломает синтаксически).
#
# Здесь мы воспроизводим это поведение локально и проверяем, что скрипт
# доходит до конца в разных ситуациях: база с пользователями, пустая база,
# свежий сервер без .git. Плюс самопроверка: заведомо сломанные варианты
# (else, case) обязаны падать — иначе проверка ничего не проверяет.
#
# Запуск: bash tests/scripts/deploy-simulation.test.sh

set -uo pipefail

BASH_BIN="$(command -v bash)"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
workflow="$repo_root/.github/workflows/deploy.yml"

# Ровно та строка, что добавляет drone-ssh (см. plugin.go, scriptCommands).
CHECK='DRONE_SSH_PREV_COMMAND_EXIT_CODE=$? ; if [ $DRONE_SSH_PREV_COMMAND_EXIT_CODE -ne 0 ]; then exit $DRONE_SSH_PREV_COMMAND_EXIT_CODE; fi;'

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
        echo "  FAIL: $3 — в выводе нет [$2]"
        failures=$((failures + 1))
    fi
}

# --- 1. Вырезаем скрипт деплоя из workflow -------------------------------
# YAML-блок "script: |" — забираем строки, отступ которых больше, чем у ключа.
# CR в конце строк (локальный чекаут на Windows) убираем: в CI и на сервер
# файл приходит с LF, и в скрипте CR был бы лишним символом.
extract_script() {
    awk '
        /^[[:space:]]*script: \|/ { inblock = 1; match($0, /[^ ]/); base = RSTART; next }
        inblock {
            sub(/\r$/, "")
            if ($0 ~ /^[[:space:]]*$/) { print ""; next }
            match($0, /[^ ]/)
            if (RSTART <= base) { exit }
            print substr($0, RSTART)
        }
    ' "$workflow"
}

if [ ! -f "$workflow" ]; then
    echo "❌ Не найден $workflow"
    exit 1
fi

extract_script > "$work/deploy.raw"
# Подстановки GitHub (secrets.*, github.repository) не являются bash-выражениями —
# на сервере они уже заменены на значения, здесь ставим безопасную заглушку.
sed -E 's/\$\{\{[^}]*\}\}/placeholder/g' "$work/deploy.raw" > "$work/deploy.sh"

lines="$(wc -l < "$work/deploy.sh" | tr -d ' ')"
if [ "$lines" -lt 20 ]; then
    echo "❌ Не удалось вырезать скрипт деплоя (получилось $lines строк)"
    exit 1
fi
echo "Скрипт деплоя: $lines строк"

# --- 2. Вставляем проверки как drone-ssh ---------------------------------
simulate() {
    # simulate <исходник> <результат>
    local src="$1" dst="$2" line trimmed
    : > "$dst"
    while IFS= read -r line || [ -n "$line" ]; do
        printf '%s\n' "$line" >> "$dst"
        trimmed="${line#"${line%%[![:space:]]*}"}"
        if [ -n "$trimmed" ]; then
            printf '%s\n' "$CHECK" >> "$dst"
        fi
    done < "$src"
}

simulate "$work/deploy.sh" "$work/deploy.sim.sh"

echo "1. Синтаксис скрипта после вставки проверок"
if "$BASH_BIN" -n "$work/deploy.sim.sh" 2> "$work/syntax.err"; then
    echo "  ok: скрипт разбирается"
else
    echo "  FAIL: синтаксическая ошибка — такую конструкцию ssh-action ломает:"
    sed 's/^/    /' "$work/syntax.err" | head -5
    failures=$((failures + 1))
fi

# --- 3. Заглушки внешних команд ------------------------------------------
make_stubs() {
    local dir="$1"
    mkdir -p "$dir"

    # git: успешно всё; при clone — «выкладываем» файлы репозитория.
    cat > "$dir/git" <<'STUB'
#!/usr/bin/env bash
if [ "${1:-}" = "clone" ]; then
    if [ -n "${STUB_REPO_FIXTURE:-}" ]; then
        cp -r "$STUB_REPO_FIXTURE/." . 2>/dev/null
    fi
fi
exit 0
STUB

    # docker и docker-compose: успешно всё; на запросе к postgres отдаём число
    # пользователей, как настоящий psql -tAc.
    cat > "$dir/docker" <<'STUB'
#!/usr/bin/env bash
# Эхо вызова — по нему тест проверяет, что деплой дошёл до нужных команд.
# Пишем в stderr: на stdout отвечает заглушка postgres (см. ниже).
echo "docker $*" >&2
for arg in "$@"; do
    if [ "$arg" = "postgres" ]; then
        printf '%s\n' "${STUB_USERS_COUNT:-11}"
        exit 0
    fi
done
exit 0
STUB
    cp "$dir/docker" "$dir/docker-compose"

    # crontab: заглушка, чтобы тест не трогал настоящий crontab раннера.
    cat > "$dir/crontab" <<'STUB'
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

    chmod +x "$dir/git" "$dir/docker" "$dir/docker-compose" "$dir/crontab"
}

run_scenario() {
    # run_scenario <имя> <сколько_пользователей> <есть_.git: yes/no>
    # Печатает код возврата скрипта деплоя; вывод остаётся в <имя>.log
    local name="$1" users="$2" with_git="$3"
    local home="$work/$name/home"
    local bin="$work/$name/bin"
    local fixture="$work/$name/fixture"
    local log="$work/$name.log"

    mkdir -p "$home/duty/scripts" "$bin" "$fixture/scripts" "$work/$name/tables"
    if [ "$with_git" = "yes" ]; then
        mkdir -p "$home/duty/.git"
    fi
    printf 'services: {}\n' > "$home/duty/docker-compose.yml"
    printf 'services: {}\n' > "$fixture/docker-compose.yml"
    cp "$repo_root/scripts/backup-db.sh" "$repo_root/scripts/install-backup-cron.sh" \
       "$repo_root/scripts/rotate-nginx-logs.sh" "$home/duty/scripts/"
    cp "$repo_root/scripts/backup-db.sh" "$repo_root/scripts/install-backup-cron.sh" \
       "$repo_root/scripts/rotate-nginx-logs.sh" "$fixture/scripts/"

    make_stubs "$bin"

    local rc=0
    HOME="$home" \
    FAKE_CRONTAB_TABLE="$work/$name/tables/crontab" \
    STUB_USERS_COUNT="$users" \
    STUB_REPO_FIXTURE="$fixture" \
    PATH="$bin:$PATH" \
    "$BASH_BIN" "$work/deploy.sim.sh" > "$log" 2>&1 || rc=$?
    echo "$rc"
}

echo "2. База с пользователями (обычный деплой на живой сервер)"
rc="$(run_scenario live-users 11 yes)"
check "0" "$rc" "скрипт дошёл до конца"
contains "$work/live-users.log" "Deployment completed successfully" "финальное сообщение"
contains "$work/live-users.log" "База инициализирована, пользователей: 11" "отчёт по числу пользователей"
contains "$work/live-users.log" "Using Docker Compose" "команда compose определена"
contains "$work/live-users.log" "docker image prune -f" "старые образы чистятся после деплоя"
contains "$work/live-users/tables/crontab" "rotate-nginx-logs.sh" "ротация логов поставлена в cron"

echo "3. Пустая база (предупреждение вместо молчаливого пропуска)"
rc="$(run_scenario empty-db 0 yes)"
check "0" "$rc" "скрипт дошёл до конца"
contains "$work/empty-db.log" "База пустая" "предупреждение о пустой базе"
contains "$work/empty-db.log" "Deployment completed successfully" "финальное сообщение"

echo "4. Свежий сервер: кода ещё нет, ветка клонирования"
rc="$(run_scenario fresh-clone 7 no)"
check "0" "$rc" "скрипт дошёл до конца"
contains "$work/fresh-clone.log" "Cloning repository" "ветка git clone"
contains "$work/fresh-clone.log" "Deployment completed successfully" "финальное сообщение"

echo "5. Самопроверка: синтетический скрипт с else обязан упасть"
cat > "$work/bad-else.sh" <<'EOF'
count=11
if [ "$count" = "0" ]; then
    echo EMPTY
else
    echo FILLED
fi
echo DONE
EOF
simulate "$work/bad-else.sh" "$work/bad-else.sim.sh"
rc=0
"$BASH_BIN" "$work/bad-else.sim.sh" > "$work/bad-else.log" 2>&1 || rc=$?
check "1" "$rc" "ветка else обрывает выполнение (как на живом деплое 85de881)"
if grep -qF "DONE" "$work/bad-else.log"; then
    echo "  FAIL: скрипт дошёл до конца — модель вставки неверна"
    failures=$((failures + 1))
else
    echo "  ok: до конца скрипт не дошёл"
fi

echo "6. Самопроверка: синтетический скрипт с case обязан не разбираться"
cat > "$work/bad-case.sh" <<'EOF'
x=a
case "$x" in
    a)
        echo A
        ;;
esac
echo DONE
EOF
simulate "$work/bad-case.sh" "$work/bad-case.sim.sh"
if "$BASH_BIN" -n "$work/bad-case.sim.sh" 2> "$work/bad-case.err"; then
    echo "  FAIL: case разобрался — модель вставки неверна"
    failures=$((failures + 1))
else
    echo "  ok: case даёт синтаксическую ошибку (как на деплое a7b6b9c)"
fi

echo
if [ "$failures" -eq 0 ]; then
    echo "Все проверки пройдены"
    exit 0
fi
echo "Провалено проверок: $failures"
exit 1
