#!/usr/bin/env bash
#
# incident-triage.sh — сбор доказательств и проверка закрепления после инцидента
# с чтением файлов на сервере.
#
# СКРИПТ ТОЛЬКО ЧИТАЕТ: он ничего не изменяет, не удаляет и не перезапускает.
# НЕ выводит содержимое .env, credentials.json и /etc/shadow — только имена/факты.
#
# Запуск на пострадавшем сервере под root:
#
#   sudo bash scripts/incident-triage.sh \
#     --from "2026-10-17 12:27" \
#     --to   "2026-10-17 22:34"
#
# Результат: каталог /root/incident-<дата-время>/ с текстовыми отчётами.
# ПОСЛЕ СБОРА: скопируйте каталог на свою машину, изучите и уберите с сервера.
#
set -uo pipefail

FROM=""
TO=""
OUT=""

usage() {
  cat <<'USAGE'
Использование: incident-triage.sh [--from "<дата время>"] [--to "<дата время>"] [--out <каталог>]

  --from  начало окна инцидента, напр. "2026-10-17 12:27"
  --to    конец окна инцидента,   напр. "2026-10-17 22:34"
  --out   каталог для отчётов (по умолчанию /root/incident-<timestamp>)
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --from) FROM="${2:-}"; shift 2 ;;
    --to)   TO="${2:-}";   shift 2 ;;
    --out)  OUT="${2:-}";  shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Неизвестный аргумент: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [ "$(id -u)" -ne 0 ]; then
  echo "ВНИМАНИЕ: запуск не от root — часть данных будет недоступна." >&2
fi

OUT="${OUT:-/root/incident-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$OUT" && chmod 700 "$OUT"

# Диапазон для journalctl (и, при необходимости, для docker logs --since).
# FROM/TO обязательно экспортируем: их подставляет `bash -c` внутри collect_shell.
export FROM TO
JARGS=()
[ -n "$FROM" ] && JARGS+=(--since "$FROM")
[ -n "$TO" ]   && JARGS+=(--until "$TO")

DOCKER_SINCE=""
if [ -n "$FROM" ]; then
  DOCKER_SINCE="$(date -d "$FROM" +%Y-%m-%dT%H:%M:%S 2>/dev/null || true)"
fi

have() { command -v "$1" >/dev/null 2>&1; }

# collect <файл> <описание> <команда...> — выполняет команду и пишет вывод в файл.
collect() {
  local file="$1" desc="$2"; shift 2
  {
    printf '\n===== %s =====\n' "$desc"
    printf '$ %s\n\n' "$*"
    "$@" 2>&1
  } >"$OUT/$file" || true
  echo "  собран: $file"
}

# collect_shell <файл> <описание> <shell-строка>
collect_shell() {
  local file="$1" desc="$2" cmd="$3"
  {
    printf '\n===== %s =====\n' "$desc"
    printf '$ %s\n\n' "$cmd"
    bash -c "$cmd" 2>&1
  } >"$OUT/$file" || true
  echo "  собран: $file"
}

collect_journal() {
  local file="$1" desc="$2"; shift 2
  if ! have journalctl; then
    printf 'journalctl недоступен на этом хосте\n' >"$OUT/$file"
    echo "  пропущен (нет journalctl): $file"
    return
  fi
  {
    printf '\n===== %s =====\n' "$desc"
    printf '$ journalctl %s %s\n\n' "${JARGS[*]:-}" "$*"
    journalctl --no-pager "${JARGS[@]}" "$@" 2>&1
  } >"$OUT/$file" || true
  echo "  собран: $file"
}

echo "Сбор отчётов в $OUT"
echo "Окно инцидента: from='${FROM:-<не задано>}' to='${TO:-<не задано>}'"
echo

# ---------------------------------------------------------------- 0. Контекст
{
  echo "===== Сбор доказательств ====="
  echo "Дата сбора:      $(date -Is)"
  echo "Окно инцидента:  ${FROM:-?} .. ${TO:-?}"
  echo "Хост:            $(hostname -f 2>/dev/null || hostname)"
  echo "uname:           $(uname -a)"
  echo "uptime:          $(uptime 2>/dev/null)"
  echo "os-release:"
  cat /etc/os-release 2>/dev/null
} >"$OUT/00-meta.txt"
echo "  собран: 00-meta.txt"

# ------------------------------------------------- 1. Пользователи и входы
collect_shell 01-users.txt "Учетные записи (прикладные) и статус хешей паролей" '
awk -F: "\$3>=1000 && \$3<65534 {print \$1, \$3, \$6, \$7}" /etc/passwd
echo "--- новые/подозрительные uid ---"
awk -F: "\$3==0 {print}" /etc/passwd
echo "--- с непустым хешем пароля (только имена) ---"
awk -F: "\$2 !~ /^[*!]*$/ {print \$1}" /etc/shadow 2>/dev/null
echo "--- файл sudo/ssh конфигов ---"
ls -la /etc/sudoers /etc/sudoers.d 2>/dev/null
'
collect_shell 02-logins.txt "Последние входы (last)" '
if command -v last >/dev/null 2>&1; then
  last -a -F | head -100
else
  echo "команда last не установлена (в Debian 13 она в пакете wtmpdb)."
  echo "Источник входов — journalctl, см. 03-journal-ssh.txt."
fi
'
collect_shell 02-logins-failed.txt "Неудачные входы" 'lastb -a 2>/dev/null | head -100'
collect 02-logins-online.txt "Кто сейчас в системе" who -a

# ------------------------------------------------------- 2. Логи аутентификации
collect_shell 03-auth-log.txt "auth.log за окно инцидента" '
f=/var/log/auth.log
[ -f "$f" ] || f=/var/log/secure
[ -f "$f" ] || { echo "auth.log не найден"; exit 0; }
echo "--- Accepted / Failed / sudo за окно ---"
grep -E "Accepted|Failed password|Invalid user|sudo:|session opened for user root" "$f" | tail -500
'
collect_journal 03-journal-ssh.txt "journalctl: sshd / sudo / login за окно" -u ssh -u sshd -u sudo
collect_journal 03-journal-root.txt "journalctl: действия root за окно" _UID=0

# ------------------------------------------------------------- 3. SSH и доступ
collect_shell 04-ssh-keys.txt "authorized_keys: файлы, mtime, отпечатки ключей" '
for k in /root/.ssh/authorized_keys /root/.ssh/authorized_keys2 \
         /home/*/.ssh/authorized_keys /home/*/.ssh/authorized_keys2; do
  [ -f "$k" ] || continue
  echo "### $k"
  stat -c "    mtime=%y mode=%a owner=%U" "$k" 2>/dev/null
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    case "$line" in \#*) echo "    $line"; continue ;; esac
    # печатаем только отпечаток и комментарий, без самого ключа
    echo "    $(printf "%s\n" "$line" | ssh-keygen -lf - 2>/dev/null | awk "{print \$1, \$2, \$3, \$4}")"
  done < "$k"
  echo
done
'
collect_shell 04-ssh-config.txt "Эффективный конфиг sshd" 'sshd -T 2>/dev/null | grep -Ei "^(port|permitrootlogin|passwordauthentication|pubkeyauthentication|authorizedkeysfile|allowusers|permitemptypasswords)" || cat /etc/ssh/sshd_config'
collect_shell 04-ssh-hostkeys.txt "Ключи хоста SSH (даты создания)" 'ls -la --time-style=long-iso /etc/ssh/ssh_host_* 2>/dev/null'

# ----------------------------------------------------------------- 4. Sudoers
collect_shell 05-sudoers.txt "Правила sudo" 'cat /etc/sudoers 2>/dev/null; echo; ls -la /etc/sudoers.d/ 2>/dev/null; head -50 /etc/sudoers.d/* 2>/dev/null'

# ------------------------------------------------------------------- 5. Cron
collect_shell 06-cron.txt "Задания cron" '
cat /etc/crontab 2>/dev/null
echo "--- /etc/cron.* ---"
for d in /etc/cron.d /etc/cron.hourly /etc/cron.daily /etc/cron.weekly /etc/cron.monthly; do
  [ -d "$d" ] && { echo "### $d"; ls -la "$d"; }
done
echo "--- crontab пользователей ---"
for u in $(cut -d: -f1 /etc/passwd); do
  c=$(crontab -l -u "$u" 2>/dev/null) && { echo "### $u"; echo "$c"; }
done
'
collect_shell 06-systemd-timers.txt "systemd timers" 'systemctl list-timers --all --no-pager 2>/dev/null'

# -------------------------------------------------------------- 6. systemd/ядро
collect_shell 07-systemd.txt "Службы: включенные и запущенные" '
systemctl list-unit-files --state=enabled --no-pager 2>/dev/null | head -100
echo "--- запущенные ---"
systemctl list-units --state=running --type=service --no-pager 2>/dev/null | head -100
'
collect_shell 07-recent-units.txt "Unit-файлы, изменённые в окне инцидента" '
find /etc/systemd /lib/systemd /usr/lib/systemd -name "*.service" -newermt "${FROM:-now -7 days}" -type f -printf "%TY-%Tm-%Td %TH:%TM  %p\n" 2>/dev/null | sort | head -100
'

# ----------------------------------------------------------------- 7. Docker
if have docker; then
  collect 08-docker-ps.txt "Все контейнеры" docker ps -a --format '{{.ID}} {{.Names}} {{.Image}} {{.Status}} {{.Ports}}'
  collect 08-docker-images.txt "Образы" docker images --format '{{.Repository}}:{{.Tag}} {{.ID}} {{.CreatedSince}} {{.Size}}'
  collect 08-docker-networks.txt "Сети" docker network ls
  collect_shell 08-docker-started.txt "Время старта контейнеров" '
docker ps -q | xargs -r docker inspect --format "{{.Name}} image={{.Config.Image}} started={{.State.StartedAt}} created={{.Created}}"
'
  collect_shell 08-docker-ports.txt "Опубликованные порты" 'docker ps --format "{{.Names}} {{.Ports}}"'
  if [ -n "$DOCKER_SINCE" ]; then
    collect_shell 08-nginx-logs.txt "Логи nginx-контейнера за окно" "
for c in duty_nginx duty_api duty_sync; do
  docker inspect \"\$c\" >/dev/null 2>&1 || continue
  echo \"##### \$c\"
  docker logs --since '$DOCKER_SINCE' \"\$c\" 2>&1 | tail -2000
done
"
  fi
else
  echo "docker не найден — пропускаю раздел 08" >"$OUT/08-docker-ps.txt"
fi

# ------------------------------------------------------------- 8. Файлы nginx
collect_shell 09-nginx-suspicious.txt "Подозрительные запросы в логах nginx" '
find /var/log -name "access.log" -o -name "access.log.*" 2>/dev/null | while read -r f; do
  echo "##### $f"
  grep -Ei "\.(env|git|ssh)|authorized_keys|/\.\./|wp-login|xmlrpc|phpmyadmin|/admin|base64|etc/passwd" "$f" | tail -100
done
find /var/lib/docker/containers -name "*-json.log" 2>/dev/null | while read -r f; do
  echo "##### $f"
  grep -Ei "\.(env|git|ssh)|authorized_keys|wp-login|phpmyadmin|base64|etc/passwd" "$f" | tail -50
done
'
collect_shell 09-host-nginx-logs.txt "Логи хостового nginx (вкл. ротацию) — единственный источник за окно" '
echo "--- файлы логов ---"
ls -la --time-style=long-iso /var/log/nginx/ 2>/dev/null
echo "--- содержимое (последние 2000 строк каждого) ---"
for f in /var/log/nginx/access.log /var/log/nginx/access.log.*; do
  [ -f "$f" ] || continue
  echo "##### $f"
  case "$f" in
    *.gz) zcat "$f" 2>/dev/null ;;
    *)    cat  "$f" 2>/dev/null ;;
  esac | tail -2000
done
'
collect_shell 09-pins-in-logs.txt "ВНИМАНИЕ: PIN в логах (query-параметры)" '
echo "Найдены запросы с pin= : файлы ниже содержат PIN в открытом виде."
echo "Обращаться как с секретом. НЕ выкладывать в тикеты и репозитории."
find /var/log -name "access.log*" 2>/dev/null | while read -r f; do
  n=$(grep -c "pin=" "$f" 2>/dev/null || true); n=${n:-0}
  [ "$n" -gt 0 ] && echo "$f : $n совпадений"
done
find /var/lib/docker/containers -name "*-json.log" 2>/dev/null | while read -r f; do
  n=$(grep -c "pin=" "$f" 2>/dev/null || true); n=${n:-0}
  [ "$n" -gt 0 ] && echo "$f : $n совпадений"
done
'

# --------------------------------------------------------- 9. Сеть и процессы
collect_shell 10-network-listen.txt "Слушающие порты (проверить 5433!)" 'ss -tulpn 2>/dev/null || netstat -tulpn 2>/dev/null'
collect_shell 10-network-established.txt "Активные исходящие соединения" 'ss -tupn state established 2>/dev/null | head -100'
collect_shell 10-processes.txt "Процессы и топ по CPU" '
ps aux --sort=-%cpu | head -30
echo "--- процессы с интересными именами ---"
ps aux | grep -Ei "miner|xmr|kdevtmpfs|kinsing|masscan|nmap|/tmp/|/dev/shm/" | grep -v grep
'
collect_shell 10-tmp-exec.txt "Исполняемые файлы в /tmp и /dev/shm" '
ls -la /tmp /dev/shm /var/tmp 2>/dev/null
find /tmp /dev/shm /var/tmp -type f -executable 2>/dev/null | head -50
'

# ------------------------------------------------------ 10. Изменённые файлы
collect_shell 11-recent-files.txt "Файлы, изменённые в окне инцидента" '
find /etc /root /home /opt /usr/local -xdev -type f \
  -newermt "${FROM:-now -7 days}" ! -newermt "${TO:-now}" \
  -printf "%TY-%Tm-%Td %TH:%TM  %p\n" 2>/dev/null | sort | head -300
'
collect_shell 11-suid.txt "SUID/SGID-файлы" 'find / -xdev \( -perm -4000 -o -perm -2000 \) -type f 2>/dev/null'
collect_shell 11-ld-preload.txt "Подмена библиотек (ld.so)" '
echo "--- /etc/ld.so.preload ---"; cat /etc/ld.so.preload 2>/dev/null
echo "--- /etc/ld.so.conf.d ---"; ls -la /etc/ld.so.conf.d/ 2>/dev/null
'
collect_shell 11-immutable.txt "Иммутабельные/подозрительные атрибуты" 'lsattr -R /etc /root /usr/local/bin 2>/dev/null | head -100'

# ------------------------------------------------------------- 11. Истории
collect_shell 12-history.txt "История команд (искать руками)" '
for f in /root/.bash_history /root/.zsh_history /home/*/.bash_history /home/*/.zsh_history; do
  [ -f "$f" ] && { echo "##### $f"; tail -300 "$f"; echo; }
done
echo "--- подозрительные команды во всей истории ---"
grep -hEi "curl|wget|base64|/dev/tcp|nc |ncat|authorized_keys|chmod \+x|crontab|useradd|passwd" \
  /root/.bash_history /home/*/.bash_history 2>/dev/null | sort -u | head -100
'

# ------------------------------------------------------------------ 12. Итог
{
  echo "===== Как читать этот отчёт ====="
  echo
  echo "1. 04-ssh-keys.txt      — ЕСТЬ ЛИ ЧУЖИЕ ключи в authorized_keys."
  echo "2. 02-logins*.txt       — входы в окне инцидента, неизвестные IP."
  echo "3. 03-journal-ssh.txt   — Accepted publickey: откуда входили."
  echo "4. 06-cron.txt, 07-*    — автозапуск: есть ли чужие задания."
  echo "5. 08-docker-*.txt      — неизвестные контейнеры/образы."
  echo "6. 11-recent-files.txt  — что менялось на диске в окне инцидента."
  echo "7. 12-history.txt       — что делали в шелле."
  echo "8. 09-pins-in-logs.txt  — где в логах лежат PIN (это тоже утечка)."
  echo
  echo "Далее по SECURITY_INCIDENT.md:"
  echo "  - снапшот диска и копию этого каталога — офлайн;"
  echo "  - ротация секретов (§4);"
  echo "  - пересборка сервера и восстановление БД из бэкапа до начала инцидента (§6)."
  echo
  echo "ПОМНИТЕ: этот каталог содержит чувствительные данные. Уберите его"
  echo "с сервера после копирования наружу."
} >"$OUT/99-README.txt"
echo "  собран: 99-README.txt"

echo
echo "Готово. Отчёты: $OUT"
echo "Скопируйте каталог офлайн и удалите его с сервера."
