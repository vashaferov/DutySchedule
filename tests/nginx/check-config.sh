#!/usr/bin/env bash
#
# Проверка nginx-конфига настоящим `nginx -t`.
#
# Зачем отдельный тест: nginx/conf.d/default.conf.nokey — единственный файл,
# опечатка в котором роняет весь сайт, а не только API, и до сих пор у него не
# было ни одной проверки. Конфиг подаётся nginx в контейнере: сертификаты
# самоподписанные (nginx -t проверяет лишь то, что файлы из ssl_certificate
# существуют и читаются), а имя `api` из proxy_pass разрешается через
# --add-host — иначе nginx -t падает на `host not found in upstream "api"`,
# хотя с конфигом всё в порядке.
#
# Локальный запуск: bash tests/nginx/check-config.sh (нужен docker)

set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
conf="$repo_root/nginx/conf.d/default.conf.nokey"
image="${NGINX_TEST_IMAGE:-nginx:alpine}"

# В Git Bash под Windows docker — это exe, поэтому путь монтирования нужен в
# windows-виде. В Linux эти строки ничего не меняют.
host_path() {
  case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*) cygpath -m "$1" ;;
    *) printf '%s' "$1" ;;
  esac
}

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# Самоподписанный сертификат. CN задаём файлом конфигурации, а не `-subj /CN=...`:
# в Git Bash аргумент, начинающийся со слэша, подменяется на windows-путь, и
# openssl получает мусор вместо CN.
mkdir -p "$work/certs"
cat > "$work/req.cnf" <<'EOF'
[req]
distinguished_name = dn
prompt = no
[dn]
CN = mediahlg.ru
EOF
openssl req -x509 -newkey rsa:2048 -nodes -days 2 \
  -config "$work/req.cnf" \
  -keyout "$work/certs/privkey.pem" -out "$work/certs/fullchain.pem" >/dev/null 2>&1
cp "$work/certs/fullchain.pem" "$work/certs/chain.pem"

# Пути к сертификатам подменяем на смонтированные.
sed 's|/etc/letsencrypt/live/mediahlg.ru|/check/certs|g' "$conf" > "$work/default.conf"

write_root_conf() { # $1 = включаемый конфиг, $2 = куда писать корневой конфиг
  cat > "$2" <<EOF
worker_processes 1;
error_log stderr warn;
pid /tmp/ngx/nginx.pid;
events { worker_connections 32; }
http {
    access_log off;
    include /check/$1;
}
EOF
}
write_root_conf default.conf "$work/nginx.conf"

nginx_t() { # $1 = имя корневого конфига внутри /check
  # MSYS_NO_PATHCONV только для docker: в Git Bash он иначе переписывает
  # `...:/check:ro` в windows-путь. В Linux переменная просто игнорируется.
  MSYS_NO_PATHCONV=1 docker run --rm \
    --add-host api:127.0.0.1 \
    -v "$(host_path "$work"):/check:ro" \
    --entrypoint sh "$image" \
    -c "mkdir -p /tmp/ngx && nginx -t -c /check/$1 -p /tmp/ngx"
}

echo "1. Конфиг из репозитория"
nginx_t nginx.conf

echo
echo "2. Контрольная проверка: копия с убранной ';' обязана не пройти"
sed 's|add_header X-Content-Type-Options "nosniff" always;|add_header X-Content-Type-Options "nosniff" always|' \
  "$work/default.conf" > "$work/broken.conf"
if cmp -s "$work/default.conf" "$work/broken.conf"; then
  echo "❌ мутация не применилась — строка для неё не найдена, тест вырожденный" >&2
  exit 1
fi
write_root_conf broken.conf "$work/nginx-broken.conf"
if nginx_t nginx-broken.conf >/dev/null 2>&1; then
  echo "❌ сломанный конфиг прошёл проверку — тест ничего не проверяет" >&2
  exit 1
fi
echo "✅ сломанный конфиг отловлен"

echo
echo "✅ конфиг nginx проходит nginx -t"

# 3. Ручка /healthz: её опрашивает healthcheck контейнера nginx (см.
# docker-compose.yml). Проверяем, что она действительно отвечает, что SPA не
# пострадал и что опрос не пишется в access-лог — журнал мы держим на хосте
# именно для разбора происшествий, и опрос раз в минуту его бы забил.
if ! command -v curl >/dev/null 2>&1; then
    echo "❌ для проверки /healthz нужен curl" >&2
    exit 1
fi

runtime_conf="$work/nginx-runtime.conf"
cat > "$runtime_conf" <<EOF
worker_processes 1;
error_log stderr warn;
pid /tmp/ngx/nginx.pid;
events { worker_connections 32; }
http {
    access_log /tmp/ngx/access.log combined;
    include /check/default.conf;
}
EOF

echo
echo "3. Ручка /healthz (её опрашивает docker healthcheck)"
container="duty_nginx_check_$$"
MSYS_NO_PATHCONV=1 docker run --rm -d --name "$container" \
  --add-host api:127.0.0.1 \
  -p "127.0.0.1::443" \
  -v "$(host_path "$work"):/check:ro" \
  --entrypoint sh "$image" \
  -c "mkdir -p /tmp/ngx && nginx -c /check/nginx-runtime.conf -p /tmp/ngx -g 'daemon off;'" >/dev/null
trap 'docker rm -f "$container" >/dev/null 2>&1 || true; rm -rf "$work"' EXIT

port=""
for _ in $(seq 1 30); do
  port=$(docker port "$container" 443/tcp 2>/dev/null | head -n1 | awk -F: '{print $NF}')
  if [ -n "$port" ] && curl -ksf -o /dev/null "https://127.0.0.1:$port/healthz" 2>/dev/null; then
    break
  fi
  sleep 1
done

if [ -z "$port" ]; then
  echo "❌ контейнер не поднялся, порт не определён" >&2
  docker logs "$container" 2>&1 | tail -20 >&2
  exit 1
fi

body=$(curl -ks "https://127.0.0.1:$port/healthz")
if [ "$body" = "ok" ]; then
  echo "✅ /healthz отвечает 200 ok"
else
  echo "❌ /healthz вернул '$body' вместо 'ok'" >&2
  exit 1
fi

spa_code=$(curl -ks -o /dev/null -w '%{http_code}' "https://127.0.0.1:$port/no-such-page")
if [ "$spa_code" = "200" ]; then
  echo "✅ SPA-фолбэк не сломан"
else
  echo "❌ SPA-фолбэк отвечает $spa_code" >&2
  exit 1
fi

# Обычный запрос — чтобы убедиться, что access-лог вообще пишется.
curl -ks -o /dev/null "https://127.0.0.1:$port/"

if MSYS_NO_PATHCONV=1 docker exec "$container" grep -q '/healthz' /tmp/ngx/access.log; then
  echo "❌ /healthz попал в access-лог" >&2
  exit 1
fi
if ! MSYS_NO_PATHCONV=1 docker exec "$container" grep -q 'GET / ' /tmp/ngx/access.log; then
  echo "❌ access-лог пуст — проверка выше ничего не значит" >&2
  exit 1
fi
echo "✅ /healthz не пишется в access-лог, обычные запросы — пишутся"

echo
echo "✅ конфиг nginx в порядке"
