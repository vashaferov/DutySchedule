#!/usr/bin/env bash
#
# Откат DutySchedule на сервере к тегу или коммиту.
#
#   bash ~/duty/scripts/rollback.sh rollback-2026-10-22
#
# Что делает:
#   1) git reset --hard <цель> — код возвращается к указанной версии;
#   2) docker compose up -d --force-recreate --build — контейнеры пересобираются;
#   3) ждёт /api/health, как деплой, и падает, если API не поднялся.
#
# Чего НЕ делает: не трогает данные в Postgres. Том pgdata остаётся, таблицы
# переживают откат. Новая таблица, созданная откатываемой версией (например
# login_attempts), просто перестаёт использоваться — старой версии она не мешает.
# Если испорчены данные, а не код, нужен scripts/restore-db.sh (см. RUNBOOK.md).
#
# .env и logs/ не отслеживаются git, поэтому reset --hard их не удаляет.
#
# ВАЖНО: откат на сервере временный. Следующий push в main снова выкатит то,
# что лежит в GitHub. Чтобы откат стал постоянным, сделайте revert-коммит
# в main — см. RUNBOOK.md, раздел «Откат».
#
# Скрипт лежит в том же репозитории, который переключает reset --hard, поэтому
# он копирует себя в /tmp и перезапускается оттуда: иначе bash дочитывал бы
# файл, которого уже нет.

set -euo pipefail

# Стандартные каталоги добавляем в конец: cron даёт урезанный PATH, но текущий
# PATH должен остаться первым — в тестах там заглушка docker, иначе вызовы
# уходят в настоящий docker и тест падает на CI.
export PATH="${PATH:-}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

COMPOSE_DIR="${COMPOSE_DIR:-$HOME/duty}"

if [ "${DUTY_ROLLBACK_SELF:-}" != "1" ]; then
    self="$(mktemp "${TMPDIR:-/tmp}/duty-rollback.XXXXXX.sh")"
    cat -- "${BASH_SOURCE[0]}" > "$self"
    chmod +x "$self"
    DUTY_ROLLBACK_SELF=1 exec bash "$self" "$@"
fi

TARGET="${1:-}"
if [ -z "$TARGET" ]; then
    echo "Использование: $0 <тег|коммит>" >&2
    echo "Доступные точки отката:" >&2
    git -C "$COMPOSE_DIR" tag --list 'rollback-*' >&2 || true
    exit 2
fi

if [ ! -d "$COMPOSE_DIR/.git" ]; then
    echo "❌ Нет репозитория в $COMPOSE_DIR (ожидается ~/duty с .git)" >&2
    exit 1
fi

cd "$COMPOSE_DIR"

echo "Сейчас: $(git rev-parse --short HEAD) $(git log -1 --pretty=%s)"

# Свежие теги с GitHub. Без сети откат к локальному тегу всё равно возможен.
if ! git fetch --tags --force origin; then
    echo "⚠️  Не удалось обновить теги с GitHub — используем локальные."
fi

if ! git rev-parse --verify --quiet "${TARGET}^{commit}" >/dev/null; then
    echo "❌ Нет такого тега или коммита: $TARGET" >&2
    echo "Локальные точки отката:" >&2
    git tag --list 'rollback-*' >&2
    exit 1
fi

target_sha="$(git rev-parse --short "${TARGET}^{commit}")"
echo "Откатываемся на: $TARGET ($target_sha)"
git reset --hard "${TARGET}^{commit}"

# Определяем команду compose так же, как deploy.yml: на сервере может быть
# только docker-compose (v1) или только docker compose (v2).
DOCKER_COMPOSE=""
if command -v docker-compose &>/dev/null; then
    DOCKER_COMPOSE="docker-compose"
fi
if [ -z "$DOCKER_COMPOSE" ]; then
    if docker compose version &>/dev/null 2>&1; then
        DOCKER_COMPOSE="docker compose"
    fi
fi
if [ -z "$DOCKER_COMPOSE" ]; then
    echo "❌ Не найдены ни docker-compose, ни docker compose" >&2
    exit 1
fi

echo "Пересобираем контейнеры ($DOCKER_COMPOSE)..."
$DOCKER_COMPOSE up -d --force-recreate --build --remove-orphans

echo "Ждём /api/health..."
api_ready=0
for i in $(seq 1 30); do
    if $DOCKER_COMPOSE exec -T api python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2).status == 200 else 1)" &>/dev/null; then
        api_ready=1
        echo "✅ API отвечает"
        break
    fi
    sleep 2
done
if [ "$api_ready" != "1" ]; then
    echo "❌ API не поднялся за 60 секунд после отката. Логи:" >&2
    $DOCKER_COMPOSE logs --tail=100 api >&2 || true
    exit 1
fi

echo "✅ Откат выполнен: $target_sha"
echo "   Данные БД не менялись. Проверьте https://mediahlg.ru/api/health и вход в приложение."
echo "   Откат временный: следующий push в main задеплоит версию из GitHub."
echo "   Чтобы закрепить — revert-коммит в main (RUNBOOK.md, «Откат»)."
