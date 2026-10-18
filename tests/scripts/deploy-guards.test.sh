#!/usr/bin/env bash
#
# Ловит опасные условия в .github/workflows/deploy.yml.
#
# Деплой едет через appleboy/ssh-action со script_stop: true, а он обрывает
# скрипт на ЛЮБОМ ненулевом коде команды — включая проверку внутри условия,
# которая законно вернула 1. Конструкция
#
#     if [ -z "$x" ] || [ -f "$y" ]; then
#
# на ложной проверке даёт код 1, и деплой падает (ровно это случилось
# 18.10.2026). Разрешены case и одиночные проверки; сложную логику лучше
# выносить в отдельный файл scripts/*.sh — там такого ограничения нет.
#
# Запуск: bash tests/scripts/deploy-guards.test.sh

set -uo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
workflow="$repo_root/.github/workflows/deploy.yml"

if [ ! -f "$workflow" ]; then
    echo "❌ Не найден $workflow"
    exit 1
fi

# Ищем if/elif, в условии которых есть || или &&. Комментарии (строки,
# начинающиеся с #) не трогаем; строки вида `if:` из GitHub Actions не
# подходят под шаблон, потому что после if идёт двоеточие, а не пробел.
find_dangerous() {
    grep -nE "^[[:space:]]*(if|elif)[[:space:]].*(\|\||&&)" "$1" || true
}

# Самопроверка детектора: без неё проверка может молча ничего не находить.
sample="$(mktemp)"
trap 'rm -f "$sample"' EXIT
cat > "$sample" <<'SAMPLE'
if [ -z "$x" ] || [ -f "$y" ]; then
    echo этот случай должен быть найден
fi
# комментарий: if [ -z "$x" ] || [ -f "$y" ]; then
if [ -z "$x" ]; then
    echo этот случай трогать нельзя
fi
case "$x" in
    "") echo case разрешён ;;
esac
SAMPLE
if [ -z "$(find_dangerous "$sample")" ]; then
    echo "❌ Детектор не нашёл заведомо опасную строку — проверка бессмысленна"
    exit 1
fi
echo "  ok: детектор ловит if с || (и не жалуется на комментарий)"

found="$(find_dangerous "$workflow")"
if [ -n "$found" ]; then
    echo "❌ В deploy.yml есть if/elif с || или && — ssh-action со script_stop оборвёт деплой:"
    echo "$found"
    echo "   Оформите проверку через case или вынесите логику в scripts/*.sh"
    exit 1
fi

echo "✅ В deploy.yml нет if/elif с || или &&"
