# RUNBOOK: деплой, база, бэкапы

Практическая инструкция на случай «что-то сломалось». Что и почему сделано —
в `SECURITY_INCIDENT.md` (безопасность) и в комментариях к `docker-compose.yml`.

## Где что лежит на сервере

| Что | Путь |
|---|---|
| Код | `~/duty` (клонируется/обновляется CI) |
| Конфиг и секреты | `~/duty/.env` (chmod 600, перезаписывается на каждом деплое) |
| Данные Postgres | docker-том `duty_pgdata` |
| Бэкапы БД | `~/duty-backups` (ежедневно, храним 14 дней) |
| Лог бэкапов | `~/duty-backups/backup.log` |
| Контейнеры | `duty_postgres`, `duty_api`, `duty_sync`, `duty_nginx` |

Контейнеры: `docker compose ps`. Логи: `docker compose logs --tail=100 api`
(аналогично `sync`, `postgres`, `nginx`).

## Деплой

Деплой запускается автоматически на push в `main` (`.github/workflows/deploy.yml`):
тесты → SSH на сервер → `git pull` → пересборка `.env` → `docker compose up -d
--force-recreate --build` → ожидание `/api/health` → проверка, что в базе есть
пользователи → настройка cron для бэкапов.

Если деплой упал:

1. `cd ~/duty && docker compose ps` — все ли контейнеры `Up`.
2. `docker compose logs --tail=100 api` — чаще всего это ошибка подключения к БД
   или отсутствующая переменная в `.env`.
3. `docker compose logs --tail=100 nginx` — если 502/504 снаружи.
4. Деплой не «откатывается» сам: актуальное состояние — текущий `main`.

### Что проверять после деплоя

- `curl -s https://mediahlg.ru/api/health` → `{"status":"ok"}`.
- В «Истории синхронизации» время — в вашем часовом поясе, а не в UTC.
- Удалённая дата уходит из листов «График» и «Репертуар» после следующей синхронизации
  (её можно дёрнуть кнопкой в UI, не дожидаясь автосинка).

## Схема базы данных

Миграций (Alembic) в проекте нет. Схему создаёт сам API при старте:
`Base.metadata.create_all` в `api/app/main.py`. Операция идемпотентная и **не
трогает существующие таблицы** — новые таблицы появятся, но новые колонки в
старых таблицах `create_all` НЕ добавит. Если в будущем понадобится новая
колонка, её придётся добавить вручную:

```bash
docker exec -it duty_postgres psql -U duty -d duty -c "ALTER TABLE ... ADD COLUMN ..."
```

Тот же `create_all` есть в `sync/http_server.py`, чтобы sync не падал, если
стартовал раньше API.

## Пустая база (авария: потерян том pgdata)

API поднимется и создаст таблицы, но в базе не будет пользователей, и войти в
приложение будет некому. Деплой об этом предупредит, но НЕ будет ничего заливать
автоматически.

Два пути:

**1. Восстановление из бэкапа (правильный путь, если бэкап есть).**
См. раздел «Восстановление из бэкапа».

**2. Импорт из Google Sheets (если бэкапа нет).** Это работает, только если
таблица актуальна: данные, которые успели появиться в приложении после
последней синхронизации, будут потеряны.

```bash
cd ~/duty
# ADMIN_NAMES — кому выдать роль админа, если в листе «Пользователи» нет колонки «Роль»
docker compose --profile tools run --rm -e ADMIN_NAMES='Имя,ДругоеИмя' migrate
```

По умолчанию скрипт только доливает недостающее и не стирает данные. Чтобы
перезалить с нуля:

```bash
docker compose --profile tools run --rm -e MIGRATE_RESET=1 migrate
```

Сервис `migrate` вынесен в профиль `tools` именно поэтому: обычный
`docker compose up -d` его НЕ запускает, и стирания данных на каждом деплое
не происходит.

## Бэкапы

Ежедневный бэкап в 03:15 (время сервера) ставится автоматически при деплое:
cron вызывает `~/duty/scripts/backup-db.sh`, дампы складываются в
`~/duty-backups`, хранятся 14 дней. Каждый дамп проверяется на читаемость
(`gzip -t` + `pg_restore --list`) до того, как старый будет признан годным —
битый бэкап хуже отсутствующего.

Проверить, что бэкапы идут:

```bash
ls -lh ~/duty-backups
tail -20 ~/duty-backups/backup.log
crontab -l | grep backup-db
```

Сделать бэкап вручную:

```bash
~/duty/scripts/backup-db.sh
```

**Бэкап лежит на том же диске, что и база.** Пока нет копии наружу, смерть
диска уносит и базу, и бэкапы. Настроить копирование можно переменной
`BACKUP_REMOTE` (например, через rclone):

```cron
15 3 * * * ENV_FILE=~/duty/.env BACKUP_REMOTE='rclone copy "$DUMP" remote:duty-backups' ~/duty/scripts/backup-db.sh >> ~/duty-backups/backup.log 2>&1
```

### Проверить, что бэкап действительно восстанавливается

Это единственный способ узнать, что бэкап рабочий. Разворачиваем в одноразовую
базу, смотрим, что данные на месте, удаляем:

```bash
cd ~/duty
DUMP=$(ls -t ~/duty-backups/duty-*.dump.gz | head -1)
echo "Проверяю $DUMP"

docker run --rm -d --name duty_restore_test \
  -e POSTGRES_PASSWORD=test -e POSTGRES_USER=duty -e POSTGRES_DB=duty postgres:15
sleep 8

gzip -dc "$DUMP" | docker exec -i duty_restore_test \
  pg_restore -U duty -d duty --no-owner
docker exec duty_restore_test psql -U duty -d duty -tAc \
  "select (select count(*) from users) as users, (select count(*) from duty_dates) as dates;"

docker rm -f duty_restore_test
```

### Восстановление из бэкапа

**Восстановление затирает текущую базу.** Всё, что появилось после снятия
дампа, будет потеряно — сначала снимаем свежий бэкап текущего состояния, чтобы
было куда вернуться:

```bash
cd ~/duty
~/duty/scripts/backup-db.sh            # сохранить текущее состояние
~/duty/scripts/restore-db.sh ~/duty-backups/duty-ГГГГММДД-ЧЧММСС.dump.gz
```

Скрипт проверяет дамп, останавливает `api` и `sync` (чтобы в базу никто не
писал), разворачивает дамп с `--clean --if-exists`, поднимает сервисы обратно.
После восстановления стоит вручную дёрнуть синхронизацию в UI и убедиться, что
имена дежурных и репертуар на месте.

## Быстрая справка

```bash
cd ~/duty

docker compose ps                     # состояние контейнеров
docker compose logs --tail=100 api    # логи API
docker compose restart api            # перезапуск API
docker compose up -d --force-recreate api sync   # пересоздать API и sync

docker exec -it duty_postgres psql -U duty -d duty     # psql в базу
docker exec duty_postgres pg_dump -U duty -d duty -F c > /tmp/manual.dump   # дамп вручную
```

Порт Postgres (5433) проброшен только на `127.0.0.1` сервера — снаружи база
недоступна, подключаться нужно через SSH-туннель:

```bash
ssh -L 5433:127.0.0.1:5433 <user>@mediahlg.ru
```
