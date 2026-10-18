#!/usr/bin/env bash
#
# Ловит в .github/workflows/deploy.yml конструкции, которые ломает
# appleboy/ssh-action при script_stop: true.
#
# Что происходит: ssh-action режет скрипт на строки и после каждой вставляет
# проверку кода возврата (см. scriptCommands в plugin.go):
#
#     DRONE_SSH_PREV_COMMAND_EXIT_CODE=$? ; if [ $... -ne 0 ]; then exit $...; fi;
#
# Отсюда два проверенных на живых деплоях запрета:
#
#   * case ... esac — вставка попадает туда, где ожидается шаблон, и скрипт
#     вообще не разбирается: "syntax error near unexpected token `;'" (a7b6b9c);
#   * else — вставка идёт первой строкой ветки и видит код 1 от ложного
#     условия, после чего завершает деплой (85de881).
#
# Можно и нужно: цепочки простых if без else, for/do/done, обычные команды.
# Сложную логику лучше уносить в scripts/*.sh — там переписывания нет и
# работает обычный bash. Поведение проверяется ещё и прогоном:
# tests/scripts/deploy-simulation.test.sh.
#
# Запуск: bash tests/scripts/deploy-guards.test.sh

set -uo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
workflow="$repo_root/.github/workflows/deploy.yml"

if [ ! -f "$workflow" ]; then
    echo "❌ Не найден $workflow"
    exit 1
fi

# case в любой форме (case "..." in).
find_case() {
    grep -nE "^[[:space:]]*case[[:space:]]" "$1" || true
}

# Ветка else: либо строка, начинающаяся с else, либо "; else" в одну строку.
# Комментарии не считаются — они начинаются с #.
find_else() {
    grep -nE "^[[:space:]]*else([[:space:]]|;|$)|;[[:space:]]*else([[:space:]]|;|$)" "$1" || true
}

# Самопроверка детекторов: без неё проверка может молча ничего не находить.
sample="$(mktemp)"
trap 'rm -f "$sample"' EXIT
cat > "$sample" <<'SAMPLE'
case "$x" in
    "") echo case запрещён ;;
esac
if [ -z "$x" ]; then
    echo так можно
else
    echo так нельзя
fi
if [ -z "$x" ]; then echo тогда; else echo теперь; fi
# комментарий: case "$x" in и else здесь безобидны
SAMPLE

if [ -z "$(find_case "$sample")" ]; then
    echo "❌ Детектор не нашёл case — проверка бессмысленна"
    exit 1
fi
echo "  ok: детектор ловит case"

if [ -z "$(find_else "$sample")" ]; then
    echo "❌ Детектор не нашёл else — проверка бессмысленна"
    exit 1
fi
echo "  ok: детектор ловит else и в отдельной строке, и в одну строку"

comment_hits="$(find_else "$sample" | grep -c 'комментарий' | head -n1)"
if [ "$comment_hits" != "0" ]; then
    echo "❌ Детектор ругается на строку-комментарий"
    exit 1
fi
echo "  ok: комментарии не считаются нарушением"

status=0
found_case="$(find_case "$workflow")"
if [ -n "$found_case" ]; then
    echo "❌ В deploy.yml есть case — ssh-action не сможет переписать скрипт:"
    echo "$found_case"
    echo "   Перепишите через if, а лучше вынесите логику в scripts/*.sh"
    status=1
fi

found_else="$(find_else "$workflow")"
if [ -n "$found_else" ]; then
    echo "❌ В deploy.yml есть ветка else — такой деплой обрывается:"
    echo "$found_else"
    echo "   Вставка проверки кода возврата первой строкой ветки видит код 1"
    echo "   от ложного условия. Разбейте на два независимых if."
    status=1
fi

if [ "$status" -eq 0 ]; then
    echo "✅ deploy.yml использует только безопасные для ssh-action конструкции"
fi
exit "$status"
