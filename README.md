# DutySchedule (MediaHLG)

Веб-приложение для ведения графика дежурств и репертуара: даты, дежурные, песни с текстами, статистика и синхронизация с Google Sheets.

- Рабочая версия: **https://mediahlg.ru**
- Репозиторий: **https://github.com/vashaferov/DutySchedule**

## Содержание

- [Возможности](#возможности)
- [Стек](#стек)
- [Архитектура](#архитектура)
- [Структура репозитория](#структура-репозитория)
- [Быстрый старт для разработки](#быстрый-старт-для-разработки)
- [Запуск через Docker Compose](#запуск-через-docker-compose)
- [Переменные окружения](#переменные-окружения)
- [API](#api)
- [База данных](#база-данных)
- [Синхронизация с Google Sheets](#синхронизация-с-google-sheets)
- [Импорт данных и миграции](#импорт-данных-и-миграции)
- [Тесты и CI](#тесты-и-ci)
- [Деплой и эксплуатация](#деплой-и-эксплуатация)
- [Безопасность](#безопасность)
- [Ограничения](#ограничения)

## Возможности

- **График дежурств**
  - даты в формате `ДД.ММ.ГГГГ` с необязательным пояснением: `10.10.2026 (утро 10-12)`;
  - карточки предстоящих дат с дежурными и репертуаром;
  - разбивка на актуальные даты и архив;
  - пагинация, статистика по прошедшим дежурствам и круговая диаграмма.

- **Дежурные**
  - пользователь может отметить или снять только себя;
  - администратор может менять дежурных на любой дате;
  - администратор добавляет и удаляет даты.

- **Репертуар**
  - песни привязаны к датам, хранятся с порядком и цветовыми метками;
  - в карточке даты репертуар свёрнут по умолчанию и раскрывается по кнопке;
  - администратор добавляет, удаляет и меняет порядок песен;
  - при добавлении песни работает поиск по названию, в том числе на мобильных устройствах.

- **Песни**
  - справочник песен с полными текстами;
  - поиск, пагинация, просмотр и копирование текста;
  - добавление, редактирование и удаление — только для администратора.

- **Пользователи и доступ**
  - вход по имени и PIN;
  - роли `user` и `admin`;
  - администратор управляет пользователями, PIN и ролями;
  - ограничение попыток входа по пользователю и по IP.

- **Интерфейс**
  - адаптивная вёрстка для телефонов и ПК;
  - светлая и тёмная темы;
  - toast-уведомления и глобальный индикатор загрузки;
  - единая вкладка «График»: дежурства и репертуар показываются вместе.

- **Интеграция**
  - фоновая синхронизация графика и репертуара с Google Sheets;
  - ручной запуск синхронизации и история запусков для администратора.

## Стек

| Слой | Технологии |
|---|---|
| Backend | Python 3.11, FastAPI 0.104, SQLAlchemy 2, Pydantic 2, Uvicorn |
| Аутентификация | JWT (HS256, `python-jose`), bcrypt |
| База данных | PostgreSQL 15 (в тестах — SQLite) |
| Frontend | HTML, CSS, ванильный JavaScript без сборки |
| Синхронизация | `gspread`, `oauth2client`, Google Sheets API |
| Инфраструктура | Docker Compose, nginx, Let's Encrypt / certbot |
| CI/CD | GitHub Actions, SSH-деплой на VDS |
| Тесты | pytest, httpx, Node.js, bash |

## Архитектура

```text
Браузер
  │ HTTPS
  ▼
nginx (80/443)
  ├── /            → статика из frontend/
  ├── /api/        → FastAPI (api:8000)
  └── /healthz     → healthcheck nginx
                         │
                         ▼
                   PostgreSQL 15
                         ▲
                         │
          sync (8001) ───┘
             │
             ▼
       Google Sheets

migrate (профиль tools) ── Google Sheets → PostgreSQL
```

- **nginx** отдаёт статику и проксирует API. Фронтенд и API находятся на одном origin, поэтому относительный путь `/api` работает без дополнительной настройки.
- **api** — FastAPI-приложение. При старте создаёт недостающие таблицы через `Base.metadata.create_all`.
- **sync** — отдельный контейнер: фоновый цикл синхронизации и HTTP-ручка `POST /run` для ручного запуска из интерфейса.
- **migrate** — ручная утилита импорта из Google Sheets. Не запускается при обычном `docker compose up`.

## Структура репозитория

```text
.
├── api/
│   ├── app/
│   │   ├── main.py              # FastAPI, CORS, подключение роутеров
│   │   ├── models.py            # SQLAlchemy-модели
│   │   ├── schemas.py           # Pydantic-схемы
│   │   ├── crud.py              # работа с БД
│   │   ├── database.py          # engine, SessionLocal
│   │   ├── security.py          # JWT, проверка ролей
│   │   ├── ratelimit.py         # ограничение попыток входа
│   │   └── routers/             # auth, duty, songs, repertoire, users, sync
│   ├── tests/                   # pytest-тесты API
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── index.html               # разметка и вся логика SPA
│   ├── styles.css               # стили, адаптивность, темы
│   └── config.js                # API_URL и размеры страниц
├── sync/
│   ├── sync.py                  # логика синхронизации с Google Sheets
│   ├── http_server.py           # HTTP-сервер и фоновый цикл
│   ├── models.py                # модели для sync
│   ├── database.py
│   ├── Dockerfile
│   └── requirements.txt
├── migrations/
│   └── add_updated_at.sql       # историческая SQL-миграция
├── nginx/conf.d/
│   └── default.conf.nokey       # шаблон конфигурации nginx
├── scripts/                     # бэкапы, восстановление, откат, ротация логов
├── tests/                       # bash- и frontend-тесты, проверки compose/nginx
├── .github/workflows/deploy.yml # CI и деплой
├── docker-compose.yml
├── Dockerfile.migrate
├── migrate_data.py              # импорт из Google Sheets
├── .env.example
├── RUNBOOK.md                   # эксплуатация: деплой, бэкапы, откат
└── SECURITY_INCIDENT.md         # разбор инцидента и меры безопасности
```

## Быстрый старт для разработки

### Требования

- Python 3.11 (версия из Docker-образа и CI)
- Node.js 18+ — только для проверки фронтенда
- Git
- Docker — для проверок nginx/compose и production-подобного запуска

### 1. Клонирование и зависимости

```bash
git clone https://github.com/vashaferov/DutySchedule.git
cd DutySchedule

python -m venv .venv
# Linux / macOS:
source .venv/bin/activate
# Windows PowerShell:
.venv\Scripts\Activate.ps1

pip install -r api/requirements.txt -r api/requirements-test.txt
```

### 2. Локальное окружение

Создайте `.env` в корне проекта:

```dotenv
DATABASE_URL=sqlite:///./dev.db
SECRET_KEY=dev-secret
CORS_ORIGINS=http://localhost:8765
```

Для локальной разработки достаточно SQLite. Для PostgreSQL укажите, например:

```dotenv
DATABASE_URL=postgresql://duty:password@localhost:5432/duty
```

### 3. Запуск API

```bash
uvicorn app.main:app --app-dir api --reload --port 8000
```

При первом старте API создаст таблицы. Проверка:

```bash
curl http://localhost:8000/api/health
# {"status":"ok"}
```

Swagger доступен по адресу **http://localhost:8000/docs**.

Создайте первого администратора (имя `admin`, PIN `1234`):

```bash
python -c "import sys; sys.path.insert(0, 'api'); from app.database import Base, engine, SessionLocal; from app import crud, schemas; Base.metadata.create_all(engine); db = SessionLocal(); crud.create_user(db, schemas.UserCreate(name='admin', pin='1234')); crud.update_user_role(db, 'admin', 'admin'); db.close()"
```

### 4. Запуск фронтенда

В `frontend/config.js` временно укажите абсолютный адрес API:

```js
const API_URL = 'http://localhost:8000/api';
```

Запустите статический сервер:

```bash
cd frontend
python -m http.server 8765
```

Откройте **http://localhost:8765**, войдите как `admin` с PIN `1234`.

> В production `API_URL` равен `/api`, потому что фронтенд и API отдаются одним nginx. Перед коммитом локальное изменение `config.js` нужно вернуть.

### 5. Тесты

Из корня проекта:

```bash
pytest api/tests -v
node tests/frontend/xss.test.js
```

Дополнительные проверки (нужны bash и Docker):

```bash
bash tests/compose/check-compose.sh
bash tests/nginx/check-config.sh
bash tests/scripts/deploy-guards.test.sh
bash tests/scripts/backup-db.test.sh
bash tests/scripts/rollback.test.sh
```

## Запуск через Docker Compose

Compose-конфигурация рассчитана на сервер с доменом `mediahlg.ru`, nginx и TLS-сертификатами. Для локальной разработки удобнее вариант выше.

```bash
cp .env.example .env
# заполните .env (см. следующий раздел)

docker compose up -d --build
docker compose ps
```

Сервисы:

| Сервис | Назначение | Порт |
|---|---|---|
| `postgres` | PostgreSQL 15 | `127.0.0.1:5433` |
| `api` | FastAPI | только внутри Docker-сети |
| `sync` | синхронизация и HTTP-ручка `/run` | `127.0.0.1:8001` |
| `nginx` | статика, API, TLS | `80`, `443` |
| `migrate` | импорт из Google Sheets | профиль `tools`, запуск вручную |

Проверка состояния:

```bash
curl -s https://mediahlg.ru/api/health
docker compose ps
```

> В репозитории лежит шаблон `nginx/conf.d/default.conf.nokey`. Для работы nginx нужен действующий `default.conf` с путями к сертификатам; на сервере конфигурация и TLS ведутся отдельно от кода.

## Переменные окружения

Шаблон — `.env.example`. Файл `.env` не коммитится и должен иметь права `600`. На сервере он перезаписывается при каждом деплое из GitHub Secrets, поэтому ручные правки там не сохранятся.

| Переменная | Обязательна | Назначение |
|---|---|---|
| `DB_NAME` | да | имя базы PostgreSQL |
| `DB_USER` | да | пользователь PostgreSQL |
| `DB_PASSWORD` | да | пароль PostgreSQL |
| `DATABASE_URL` | для локального запуска | строка подключения; в Compose собирается из `DB_*` |
| `JWT_SECRET` | да | ключ подписи JWT; в контейнере API передаётся как `SECRET_KEY` (локально API читает `SECRET_KEY`) |
| `LOGIN_MAX_FAILURES_PER_USER` | нет | неудачных попыток на пользователя, по умолчанию `5` |
| `LOGIN_MAX_FAILURES_PER_IP` | нет | неудачных попыток на IP, по умолчанию `60` |
| `LOGIN_WINDOW_MINUTES` | нет | окно ограничения в минутах, по умолчанию `15` |
| `SPREADSHEET_ID` | для синхронизации | ID Google-таблицы |
| `GOOGLE_SHEETS_CREDENTIALS` | для синхронизации | JSON сервисного аккаунта в base64 (или JSON-строка) |
| `CORS_ORIGINS` | нет | разрешённые origin через запятую, по умолчанию `https://mediahlg.ru` |
| `ADMIN_NAMES` | нет | имена, которым импорт выдаст роль администратора (только для `migrate`) |
| `TOKEN_TTL_HOURS` | нет | срок жизни JWT в часах, по умолчанию `168` (7 дней) |

Сгенерировать `JWT_SECRET`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Получить base64 из файла сервисного аккаунта:

```bash
base64 -w0 credentials.json
```

На Windows:

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("credentials.json"))
```

## API

Все ручки доступны с префиксом `/api`. Авторизация — заголовок:

```http
Authorization: Bearer <token>
```

Токен выдаётся после `POST /api/auth/login`.

### Аутентификация

| Метод | Путь | Доступ | Описание |
|---|---|---|---|
| `POST` | `/api/auth/login` | все | вход по `name` и `pin`, возвращает токен и роль |
| `GET` | `/api/auth/me` | авторизованные | проверка токена |
| `GET` | `/api/auth/getUserNames` | все | список имён для формы входа |
| `GET` | `/api/auth/getUsers` | admin | список пользователей с ролями |

### График

| Метод | Путь | Доступ | Описание |
|---|---|---|---|
| `GET` | `/api/duty/matrix` | все | даты, имена и матрица дежурств |
| `POST` | `/api/duty/dates` | admin | создать дату |
| `DELETE` | `/api/duty/dates/{date_str}` | admin | удалить дату со связанными данными |
| `POST` | `/api/duty/toggle` | пользователь / admin | назначить или снять дежурство |

Пример создания даты:

```json
{
  "date_str": "10.10.2026 (утро 10-12)"
}
```

Пример изменения дежурства:

```json
{
  "date_str": "10.10.2026",
  "user_name": "Имя",
  "value": true
}
```

Пользователь может менять только своё дежурство; администратор — любое.

### Песни

| Метод | Путь | Доступ | Описание |
|---|---|---|---|
| `GET` | `/api/songs/` | все | список песен с текстами |
| `POST` | `/api/songs/` | admin | добавить песню |
| `PUT` | `/api/songs/{name}` | admin | обновить текст песни |
| `DELETE` | `/api/songs/{name}` | admin | удалить песню |

Текст передаётся в теле запроса:

```json
{
  "text": "Полный текст песни..."
}
```

### Репертуар

| Метод | Путь | Доступ | Описание |
|---|---|---|---|
| `GET` | `/api/repertoire/` | все | репертуар по всем датам |
| `PUT` | `/api/repertoire/{date_str}` | admin | заменить список песен на дате |
| `DELETE` | `/api/repertoire/{date_str}/{song_name}` | admin | удалить песню из репертуара даты |

Пример замены репертуара:

```json
{
  "songs": ["Песня 1", "Песня 2"]
}
```

### Пользователи

| Метод | Путь | Доступ | Описание |
|---|---|---|---|
| `GET` | `/api/users/` | admin | список пользователей |
| `POST` | `/api/users/` | admin | создать пользователя |
| `PUT` | `/api/users/{name}/pin` | admin | сменить PIN |
| `PUT` | `/api/users/{name}/role` | admin | сменить роль (`user` / `admin`) |
| `DELETE` | `/api/users/{name}` | admin | удалить пользователя |

### Синхронизация и служебные ручки

| Метод | Путь | Доступ | Описание |
|---|---|---|---|
| `POST` | `/api/sync/run` | admin | запустить синхронизацию |
| `GET` | `/api/sync/history?limit=50` | admin | история синхронизаций |
| `GET` | `/api/health` | все | healthcheck API |
| `GET` | `/healthz` | все | healthcheck nginx |

## База данных

Основные таблицы:

| Таблица | Назначение |
|---|---|
| `users` | пользователи, bcrypt-хеши PIN, роли |
| `duty_dates` | даты графика, уникальная строка даты |
| `duty_assignments` | связь «дата — дежурный» |
| `songs` | справочник песен и тексты |
| `repertoire` | песни на дату с порядком |
| `date_colors` | цветовые метки дат |
| `sync_metadata` | флаги и служебные значения синхронизации |
| `sync_history` | история запусков синхронизации |
| `login_attempts` | неудачные попытки входа для rate limit |

Схему создаёт API при старте через `Base.metadata.create_all`. Alembic в проекте нет:

- новые таблицы создаются автоматически;
- новые колонки в существующих таблицах автоматически **не** добавляются;
- для старых баз используйте SQL из `migrations/`, например `migrations/add_updated_at.sql`;
- изменения схемы на живой базе применяйте вручную через `psql`.

## Синхронизация с Google Sheets

Сервис `sync`:

- проверяет флаг изменений в `sync_metadata` и синхронизирует листы «График» и «Репертуар»;
- в Docker-окружении фоновая проверка выполняется раз в 60 секунд (`SYNC_INTERVAL`);
- при изменениях перезаписывает соответствующие листы;
- при удалении даты выполняет полную перезаливку, потому что удалённые строки не оставляют `updated_at`;
- пишет историю запусков: кто запустил, что изменилось, статус и текст ошибки.

Ручной запуск доступен администратору в интерфейсе или через `POST /api/sync/run`. Запрос идёт в `sync:8001/run`, токен администратора передаётся как есть.

Лист «Пользователи» используется только при импорте. PIN-коды в Google Sheets не выгружаются.

Формат листов:

- **График** — первая колонка «Дата», далее имена пользователей, значения `TRUE` / `FALSE`;
- **Репертуар** — «Дата», «Песни» (по одной в строке), «Цвета» (по одному в строке).

Для синхронизации нужны `SPREADSHEET_ID`, `GOOGLE_SHEETS_CREDENTIALS` и доступ сервисного аккаунта к таблице.

## Импорт данных и миграции

Импорт из Google Sheets выполняет отдельный сервис `migrate`:

```bash
docker compose --profile tools run --rm migrate
```

По умолчанию он **только добавляет недостающие записи** и не стирает существующие данные. Существующие пользователи, песни и даты не перезаписываются.

Очистка основных таблиц перед импортом (опасно, только осознанно):

```bash
docker compose --profile tools run --rm -e MIGRATE_RESET=1 migrate
```

Выдать роль администратора именам, которых нет в колонке «Роль»:

```bash
docker compose --profile tools run --rm -e ADMIN_NAMES='Имя,ДругоеИмя' migrate
```

Импортируются листы:

- «Пользователи» — имя, PIN, роль;
- «График» — даты и дежурные;
- «Песни» — названия и тексты;
- «Репертуар» — песни и цвета по датам.

## Тесты и CI

### Локально

```bash
# API
pytest api/tests -v

# Регрессия на stored XSS во фронтенде
node tests/frontend/xss.test.js

# Проверки инфраструктуры
bash tests/compose/check-compose.sh
bash tests/nginx/check-config.sh
bash tests/scripts/deploy-guards.test.sh
bash tests/scripts/backup-db.test.sh
bash tests/scripts/rollback.test.sh
```

API-тесты используют SQLite и не требуют PostgreSQL. Проверки nginx и compose требуют Docker; bash-тесты удобно запускать в Linux, WSL или Git Bash.

### GitHub Actions

Workflow `.github/workflows/deploy.yml` на каждый push в `main`:

1. запускает `pytest api/tests -v`;
2. проверяет фронтенд через `node tests/frontend/xss.test.js`;
3. проверяет синтаксис и тесты bash-скриптов;
4. проверяет nginx-конфиг настоящим `nginx -t`;
5. проверяет `docker-compose.yml`;
6. выполняет тест установки cron и симуляцию деплоя;
7. при успехе деплоит на VDS по SSH.

Для деплоя нужны GitHub Secrets:

`VDS_HOST`, `VDS_USER`, `SSH_PRIVATE_KEY`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `JWT_SECRET`, `SPREADSHEET_ID`, `GOOGLE_SHEETS_CREDENTIALS`.

## Деплой и эксплуатация

Деплой запускается автоматически при push в `main`:

- сервер обновляет код в `~/duty`;
- создаёт `.env` из GitHub Secrets;
- делает бэкап БД;
- пересобирает и перезапускает контейнеры;
- ждёт `/api/health`;
- проверяет HTTPS через `/healthz`;
- предупреждает, если база пустая;
- ставит cron для бэкапов и ротации логов nginx.

Полезные команды на сервере:

```bash
cd ~/duty

docker compose ps
docker compose logs --tail=100 api
docker compose logs --tail=100 sync

curl -s https://mediahlg.ru/api/health
```

Бэкапы, восстановление, откат к тегу и разбор инцидентов описаны в **[RUNBOOK.md](RUNBOOK.md)**. Там же — схема БД, работа с пустой базой и логи nginx.

## Безопасность

- PIN хранится только в виде bcrypt-хеша и передаётся в теле запросов, а не в query string.
- Вместо PIN в каждом запросе используется JWT; срок жизни по умолчанию — 7 дней.
- Роль при каждом запросе берётся из базы, поэтому разжалованный администратор сразу теряет права.
- Неудачные попытки входа ограничены по имени пользователя и по IP; при превышении возвращается `429`.
- PostgreSQL, API и sync не опубликованы в интернет: Postgres доступен только на `127.0.0.1:5433`, sync — на `127.0.0.1:8001`, API — только через nginx.
- Секреты лежат в `.env` с правами `600` и не коммитятся. `credentials.json` также исключён из git.
- На фронтенде данные экранируются перед вставкой в HTML; регрессия проверяется тестом `tests/frontend/xss.test.js`.
- nginx добавляет `Content-Security-Policy`, `X-Content-Type-Options` и запрещает встраивание в iframe.
- Детали инцидента и принятые меры: **[SECURITY_INCIDENT.md](SECURITY_INCIDENT.md)**.

## Ограничения

- Схема БД обновляется через `create_all`; для новых колонок нужна ручная SQL-миграция.
- Приложение рассчитано на один сервер и один экземпляр PostgreSQL; горизонтального масштабирования и внешнего хранилища сессий нет.
- Синхронизация с Google Sheets односторонняя: приложение перезаписывает листы «График» и «Репертуар», а не читает изменения из них.
- Лимит «2 дежурных на дату» задан в интерфейсе (`MAX_PER_DAY` в `frontend/config.js`) и не является жёстким ограничением БД.
