# Ecology — поиск объектов обращения с отходами

Монорепозиторий: **фронтенд** на Next.js и **бэкенд** на Python (FastAPI): загрузка PDF реестров с сайта [ecoinfo.by](https://www.ecoinfo.by/) (вручную), парсинг, кэш в PostgreSQL, поиск и семь ближайших объектов, карта OpenStreetMap (Leaflet), геокодинг Nominatim.

## Требования

- **Docker** и **Docker Compose** (plugin `docker compose`) — для запуска всего стека одной командой
- либо для разработки без Docker:
  - **Node.js** 20+ (для `web/`)
  - **Python** 3.11+ (для `server/`)
  - **PostgreSQL** 16+
- Интернет (тайлы карты, Nominatim при первичной загрузке реестра)

## Структура каталогов

| Каталог    | Назначение |
|-----------|------------|
| `web/`    | Next.js 16, интерфейс |
| `server/` | FastAPI, парсинг PDF, кэш |
| `docker/` | Конфигурация nginx для режима «один URL» |
| `docker-compose.yml` | Сервисы: PostgreSQL, API, фронт, nginx |

## Запуск в Docker (весь проект)

Один внешний порт (по умолчанию **8080**): nginx проксирует фронт и API (`/api/`, `/health`, `/docs`).

### Что поднимается

| Сервис | Роль |
|--------|------|
| `postgres` | PostgreSQL 16, данные в volume `ecology_postgres_data` |
| `api` | FastAPI; при старте выполняется `python -m alembic upgrade head`, затем uvicorn |
| `web` | Next.js (production build, `standalone`) |
| `edge` | nginx, проброс порта на хост |

### Подготовка (рекомендуется)

В **корне репозитория** (рядом с `docker-compose.yml`) можно создать файл `.env` — переменные из него подхватит Compose.

Пример (скопируйте и подставьте свои значения):

```env
# Обязательно смените в продакшене
JWT_SECRET=длинный-случайный-секрет

# Почта и пароль владельца (bootstrap-админ при старте API)
BOOTSTRAP_OWNER_EMAIL=you@example.com
BOOTSTRAP_OWNER_PASSWORD=не_менее_8_символов

# CORS: тот же scheme+host+port, с которого открываете UI (localhost и 127.0.0.1 для браузера — разные origins).
# Сборка web в compose использует относительные `/api/...` за nginx, чтобы не ломать cookie при смене host.
PUBLIC_ORIGIN=http://localhost:8080

# Опционально: другой порт на хосте
# HTTP_PORT=8080

# Опционально: своя БД (по умолчанию postgres/postgres, БД ecology)
# POSTGRES_USER=postgres
# POSTGRES_PASSWORD=postgres
# POSTGRES_DB=ecology
```

Строка `DATABASE_URL` для контейнера `api` **задаётся внутри** `docker-compose.yml` (хост `postgres`, порт `5432`); менять её нужно только если вы правите compose или выносите БД наружу.

### Команды

Сборка и запуск в фоне:

```bash
docker compose up --build -d
```

**Windows (PowerShell)** — то же самое из каталога с `docker-compose.yml`:

```powershell
cd D:\Projects\ecology
docker compose up --build -d
```

Откройте в браузере: [http://localhost:8080](http://localhost:8080) (или `http://localhost:${HTTP_PORT}`).

Проверка API через nginx:

```bash
curl http://localhost:8080/health
```

### Данные после первого запуска

Таблицы создаются миграциями автоматически. Пользователей и кэш из старых JSON (если они лежат в volume `ecology_api_data` на пути `/app/app/data/` внутри API) можно один раз импортировать:

```bash
docker compose exec api python -m app.jobs.import_auth_users
docker compose exec api python -m app.jobs.import_registry_cache
```

Вторую команду выполняйте только если нужны уже сохранённые `user_registry_cache.json` / `geocode_cache.json` из volume.

### Логи и остановка

```bash
docker compose logs -f api
docker compose logs -f edge
docker compose down
```

Полный сброс контейнеров и **именованных** томов (удалит БД и файлы в `ecology_api_data`):

```bash
docker compose down -v
```

## Запуск бэкенда (Python)

1. Перейдите в каталог сервера и установите зависимости:

```bash
cd server
python -m venv .venv
```

**Windows (PowerShell):**

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -r requirements.txt
```

**macOS / Linux:**

```bash
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
```

2. (Необязательно) скопируйте `server/.env.example` в `server/.env` и укажите `DATABASE_URL`.

3. Примените миграции (из каталога `server`, с активированным venv):

```bash
cd server
python -m alembic upgrade head
```

В **PowerShell** не используйте `cd server && …` в старых версиях — выполните команды по очереди или через `;` (`cd server; python -m alembic upgrade head`). Команда `python -m alembic` нужна, если скрипт `alembic` не в `PATH`.

4. (Опционально) перенесите текущих пользователей из JSON:

```bash
cd server
python -m app.jobs.import_auth_users
```

Для переноса уже сохранённого кэша реестра и геокэша из JSON в PostgreSQL:

```bash
cd server
python -m app.jobs.import_registry_cache
```

5. Запустите API из каталога `server`:

```bash
cd server
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

На Windows используйте **`python -m uvicorn`**, если команда `uvicorn` не находится.

Проверка: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

## Запуск фронтенда (Next.js)

```bash
cd web
npm install
```

Скопируйте `web/.env.example` в `web/.env.local`, при необходимости укажите `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000`.

```bash
npm run dev
```

Сайт: [http://localhost:3000](http://localhost:3000).

## Реестр PDF (главная страница)

1. Скачайте с [страницы реестров ecoinfo.by](https://www.ecoinfo.by/%D0%B0%D0%B4%D0%BC%D0%B8%D0%BD%D0%B8%D1%81%D1%82%D1%80%D0%B0%D1%82%D0%B8%D0%B2%D0%BD%D1%8B%D0%B5-%D0%BF%D1%80%D0%BE%D1%86%D0%B5%D0%B4%D1%83%D1%80%D1%8B/%D1%80%D0%B5%D0%B5%D1%81%D1%82%D1%80%D1%8B) файлы «Реестр объектов по использованию отходов (часть I)» и при необходимости «(часть II)».
2. На сайте нажмите **«Загрузить реестр»** и выберите один или несколько PDF.
3. Сервер парсит документы, геокодирует адреса (с паузой между запросами к Nominatim), сохраняет структурированные данные в таблицу `registry_records`, координаты адресов — в `geocode_cache`.
4. В поиске расстояние считается **по дорогам** через OSRM (`DISTANCE_MODE=road`, по умолчанию); при недоступном роутинге будет fallback «по прямой».
5. Повторная загрузка не обязательна: поиск идёт из кэша, пока вы не очистите его (`DELETE /api/v1/registry/cache`) или не загрузите реестр снова (кэш перезапишется).

Большие PDF обрабатываются долго (тысячи записей и геокодирование) — на интерфейсе отображаются прогресс и skeleton списка.

## Полезные команды

| Команда | Где | Назначение |
|--------|-----|------------|
| `docker compose up --build -d` | корень репозитория | Сборка и запуск всего стека |
| `docker compose down` | корень | Остановка контейнеров |
| `docker compose logs -f api` | корень | Логи бэкенда |
| `npm run lint` | `web/` | ESLint |
| `npm run build` | `web/` | Сборка |

## Основные эндпоинты API

- `GET /health`
- `POST /api/v1/objects/search` — выборка из кэша реестра, до `REGISTRY_CLOSEST_LIMIT` ближайших (по умолчанию 7)
- `GET /api/v1/geocode/reverse`, `GET /api/v1/geocode/search`
- `POST /api/v1/pdf/extract` — разовое извлечение текста из PDF
- `POST /api/v1/registry/import` — загрузка PDF реестра (multipart, поле `files`)
- `GET /api/v1/registry/import/{job_id}` — статус фоновой обработки
- `GET /api/v1/registry/cache` — метаданные кэша
- `DELETE /api/v1/registry/cache` — очистить кэш реестра

## Устранение неполадок

- **Docker: порт 8080 занят** — задайте в `.env` у корня, например: `HTTP_PORT=8081`, затем `docker compose up -d` заново.
- **Docker: API не стартует** — смотрите `docker compose logs api`: часто это недоступная БД до healthcheck; в compose для `postgres` включён `healthcheck`, `api` ждёт `service_healthy`.
- **Нет строк в таблице** — загрузите реестр кнопкой на главной или проверьте, что API доступен.
- **Долгая обработка** — нормально для полных реестров; геокодирование ограничено политикой Nominatim (`REGISTRY_GEOCODE_DELAY_SEC`).
- **User-Agent** — задайте осмысленный `NOMINATIM_USER_AGENT` в окружении для продакшена.

## Лицензии и данные

Тайлы: © [OpenStreetMap](https://www.openstreetmap.org/copyright). Геокодинг: [Nominatim](https://nominatim.org/) — [политика использования](https://operations.osmfoundation.org/policies/nominatim/). Расстояние по дорогам: [OSRM](https://project-osrm.org/) (по умолчанию [router.project-osrm.org](https://router.project-osrm.org/)). Содержание реестров PDF определяется их правообладателями.
