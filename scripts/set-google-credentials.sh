#!/usr/bin/env bash
#
# set-google-credentials.sh — обновление ключа сервисного аккаунта Google.
#
# Обновляет сразу два места на сервере:
#   1) sync/credentials.json         (файл, монтируется в контейнер sync)
#   2) GOOGLE_SHEETS_CREDENTIALS     (base64 в .env — в коде этот источник приоритетнее файла)
#
# НЕ обновляет GitHub Secret — это делается руками, и это ОБЯЗАТЕЛЬНО:
# deploy.yml перезаписывает .env при каждом деплое, иначе следующий push в main
# вернёт в .env старый (уже удалённый) ключ.
#
# Запуск из каталога с docker-compose.yml (например, ~/duty):
#   bash scripts/set-google-credentials.sh /путь/к/новому-ключу.json
#   bash scripts/set-google-credentials.sh /путь/к/новому-ключу.json --restart
#
set -euo pipefail

# Ключ, скомпрометированный 17.10.2026: подставить его по ошибке нельзя.
OLD_KEY_ID="a35827140ad11cf5d8de5a4f271c0c76c3986f77"

KEY_JSON="${1:-}"
RESTART="${2:-}"
APP_DIR="${APP_DIR:-$(pwd)}"
ENV_FILE="$APP_DIR/.env"
CRED_FILE="$APP_DIR/sync/credentials.json"

die() { echo "ОШИБКА: $*" >&2; exit 1; }

[ -n "$KEY_JSON" ] || die "укажите путь к новому JSON-ключу: bash $0 /путь/к/ключу.json [--restart]"
[ -f "$KEY_JSON" ] || die "файл не найден: $KEY_JSON"
[ -f "$ENV_FILE" ] || die ".env не найден: $ENV_FILE (приложение развёрнуто в $APP_DIR?)"

echo "Каталог приложения: $APP_DIR"

# --- 1. Проверяем ключ и нормализуем его -------------------------------------
# BOM в начале файла ломает и python-приложение, и base64-декодирование,
# поэтому здесь ключ перезаписывается в чистый UTF-8 без BOM.
KEY_CLEAN="$(mktemp)"
trap 'rm -f "$KEY_CLEAN"' EXIT

if command -v python3 >/dev/null 2>&1; then
  OUT="$(python3 - "$KEY_JSON" "$KEY_CLEAN" <<'PY'
import json, sys
src, dst = sys.argv[1], sys.argv[2]
raw = open(src, "rb").read()
if raw.startswith(b"\xef\xbb\xbf"):
    print("  (в файле был BOM — удалён)", file=sys.stderr)
data = json.loads(raw.decode("utf-8-sig"))
assert data.get("type") == "service_account", "type != service_account"
assert data.get("private_key"), "нет private_key"
assert data.get("private_key_id"), "нет private_key_id"
open(dst, "wb").write(json.dumps(data).encode("utf-8"))
print(data["private_key_id"] + "\t" + data.get("client_email", "?"))
PY
)" || die "не удалось разобрать JSON ключа (сообщение выше)"
  NEW_ID="$(printf '%s' "$OUT" | cut -f1)"
  NEW_EMAIL="$(printf '%s' "$OUT" | cut -f2)"
else
  echo "  (python3 не найден — проверяю ключ через grep)"
  sed '1s/^\xEF\xBB\xBF//' "$KEY_JSON" > "$KEY_CLEAN"
  grep -q '"type": *"service_account"' "$KEY_CLEAN" || die "это не ключ сервисного аккаунта"
  NEW_ID="$(grep -o '"private_key_id": *"[^"]*"' "$KEY_CLEAN" | head -1 | sed 's/.*: *"//; s/"$//')"
  NEW_EMAIL="$(grep -o '"client_email": *"[^"]*"' "$KEY_CLEAN" | head -1 | sed 's/.*: *"//; s/"$//')"
fi

[ -n "${NEW_ID:-}" ] || die "не удалось определить private_key_id"
echo "Новый ключ:"
echo "  client_email    = ${NEW_EMAIL:-?}"
echo "  private_key_id  = $NEW_ID"

[ "$NEW_ID" != "$OLD_KEY_ID" ] || die "это СТАРЫЙ скомпрометированный ключ. Возьмите файл нового ключа."

if grep -q "$OLD_KEY_ID" "$ENV_FILE" 2>/dev/null || grep -q "$OLD_KEY_ID" "$CRED_FILE" 2>/dev/null; then
  echo "  (в .env/credentials.json сейчас лежит старый ключ — заменяем)"
fi

# --- 2. Резервные копии -------------------------------------------------------
STAMP="$(date +%Y%m%d-%H%M%S)"
cp -p "$ENV_FILE" "$ENV_FILE.bak-$STAMP"
echo "Бэкап .env: $ENV_FILE.bak-$STAMP"
if [ -f "$CRED_FILE" ]; then
  cp -p "$CRED_FILE" "$CRED_FILE.bak-$STAMP"
  echo "Бэкап файла: $CRED_FILE.bak-$STAMP"
fi

# --- 3. Файл credentials.json -------------------------------------------------
mkdir -p "$(dirname "$CRED_FILE")"
if command -v install >/dev/null 2>&1; then
  install -m 600 "$KEY_CLEAN" "$CRED_FILE"
else
  cp "$KEY_CLEAN" "$CRED_FILE" && chmod 600 "$CRED_FILE"
fi
echo "Обновлён файл: $CRED_FILE (права 600)"

# --- 4. base64 в .env ---------------------------------------------------------
if base64 --help 2>&1 | grep -q -- '-w'; then
  B64="$(base64 -w0 "$KEY_CLEAN")"
else
  B64="$(openssl base64 -A -in "$KEY_CLEAN")"
fi
[ -n "$B64" ] || die "не удалось закодировать ключ в base64"

# awk безопаснее sed: base64 содержит '/' и '=', но не содержит '\'
awk -v key="$B64" '
  BEGIN { found = 0 }
  /^GOOGLE_SHEETS_CREDENTIALS=/ { print "GOOGLE_SHEETS_CREDENTIALS=" key; found = 1; next }
  { print }
  END { if (!found) print "GOOGLE_SHEETS_CREDENTIALS=" key }
' "$ENV_FILE" > "$ENV_FILE.tmp"
mv "$ENV_FILE.tmp" "$ENV_FILE"
chmod 600 "$ENV_FILE"
echo "Обновлён $ENV_FILE (права 600, длина base64 = ${#B64})"

# --- 5. Не остался ли старый ключ (кроме наших бэкапов) ------------------------
LEFT="$(grep -rl "$OLD_KEY_ID" "$APP_DIR" 2>/dev/null \
  | grep -v "\.bak-$STAMP$" || true)"
if [ -n "$LEFT" ]; then
  echo
  echo "ВНИМАНИЕ: старый ключ ещё упоминается в:"
  echo "$LEFT"
fi

# --- 6. Перезапуск (по флагу) -------------------------------------------------
if [ "$RESTART" = "--restart" ]; then
  echo
  echo "Перезапускаю sync (аутентификация происходит при старте контейнера)..."
  ( cd "$APP_DIR" && docker compose up -d --force-recreate sync )
  echo "Логи: docker compose logs --tail=50 sync"
fi

cat <<'NEXT'

============================================================
ОСТАЛОСЬ СДЕЛАТЬ РУКАМИ
============================================================
1) GitHub → Settings → Secrets and variables → Actions →
   обновить GOOGLE_SHEETS_CREDENTIALS значением base64 от нового ключа.
   ЭТО ОБЯЗАТЕЛЬНО: иначе следующий push в main вернёт в .env СТАРЫЙ ключ.

   base64 одной строкой:
     Linux:   base64 -w0 new-key.json
     Windows: [Convert]::ToBase64String([IO.File]::ReadAllBytes("new-key.json"))

2) Проверить в Google Cloud, что СТАРЫЙ ключ удалён
   (private_key_id a35827140ad11cf5d8de5a4f271c0c76c3986f77),
   и что таблица расшарена на client_email сервисного аккаунта
   с правом редактирования: sync делает clear + append.

3) Обновить локальную копию на рабочей машине (.env и sync/credentials.json).

4) Перезапустить и проверить:
     docker compose up -d --force-recreate sync
     docker compose logs --tail=50 sync

5) Убедиться, что старого ключа нет нигде (включая снапшоты и бэкапы):
     grep -rl a35827140ad11cf5d8de5a4f271c0c76c3986f77 ~/
NEXT
