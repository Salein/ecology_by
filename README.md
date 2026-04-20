# Ecology — поиск объектов обращения с отходами

Монорепозиторий приложения для поиска объектов по видам отходов и расстоянию:
- **Frontend**: Next.js 16 (`web/`)
- **Backend**: FastAPI + SQLAlchemy + Alembic (`server/`)
- **DB**: PostgreSQL 16
- **Edge**: nginx (единый URL для UI + API)

Данные попадают в систему через импорт PDF реестров с [ecoinfo.by](https://www.ecoinfo.by/), затем очищаются, дедуплицируются, геокодируются и ищутся с ранжированием по расстоянию.

## Что нового

- Оптимизирован импорт реестров: потоковый парсинг, batch insert, адаптивные checkpoint-ы, кеши геокодинга.
- Усилен парсер PDF для сложных/«битых» блоков, добавлены fallback-режимы и доп. эвристики по owner/object/address.
- Улучшено качество отображения полей в UI (`Собственник`, `Объект`, `Адрес`, `Телефоны`) и добавлены unit-тесты форматтеров.
- Добавлены метрики хода импорта в UI (progress, скорость, ETA, geocode counters).
- Улучшен запуск и публикация: quick tunnel профиль в Docker Compose и скрипт обслуживания `docker-reset-and-up.ps1`.

## Текущее состояние проекта

На текущем этапе реализовано:
- устойчивый парсинг PDF реестров (часть I/II) с fallback-стратегиями;
- потоковый импорт и оптимизации нагрузки (batch insert, checkpoint policy, кеши геокодинга);
- корректная обработка флага `accepts_external_waste`;
- быстрый поиск с фильтрами и защитой от дублей;
- доработанный UI: чистые поля `Собственник/Объект/Адрес/Телефоны`, прогресс и метрики импорта;
- запуск через Docker Compose с локальным URL и Cloudflare tunnel профилями.

## Структура

| Путь | Назначение |
|---|---|
| `web/` | Next.js UI |
| `server/` | FastAPI, парсер, поиск, импорт |
| `server/alembic/` | миграции БД |
| `docker/` | Dockerfile и nginx edge |
| `docker-compose.yml` | orchestration стека |
| `docker-reset-and-up.ps1` | быстрый reset/cleanup + повторный запуск |

## Быстрый старт (Docker)

Из корня проекта:

```bash
docker compose up -d --build
```

Открыть:
- UI: [http://localhost:8080](http://localhost:8080)
- health: [http://localhost:8080/health](http://localhost:8080/health)

Проверить сервисы:

```bash
docker compose ps
```

Остановить:

```bash
docker compose down
```

## Публичный доступ по одноразовой ссылке (Quick Tunnel)

Поднять с quick tunnel:

```bash
docker compose --profile tunnel up -d --build
```

Посмотреть актуальный URL:

```bash
docker compose logs --tail=80 cloudflared
```

В логах будет ссылка вида:
`https://xxxx-xxxx.trycloudflare.com`

Важно:
- не запускайте одновременно `tunnel` и `tunnel-token`;
- если профиль `tunnel-token` был запущен раньше и перезапускается с ошибкой, остановите его:

```bash
docker compose --profile tunnel-token stop cloudflared-token
```

## Конфигурация (корневой `.env`)

Минимально рекомендуется задать:

```env
JWT_SECRET=длинный_случайный_секрет_не_менее_32_байт
BOOTSTRAP_OWNER_EMAIL=you@example.com
BOOTSTRAP_OWNER_PASSWORD=your_password
PUBLIC_ORIGIN=http://localhost:8080
```

Дополнительно (опционально):
- `HTTP_PORT` (если 8080 занят)
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`
- `NOTIFY_WEBHOOK_URL` (для уведомлений quick tunnel)

## Импорт реестров PDF

1. В UI нажмите **«Загрузить реестр»** и выберите PDF (часть I/II).
2. Импорт идет в фоне; статус доступен по `job_id`.
3. В интерфейсе показываются прогресс и runtime-метрики (скорость, ETA, geocode stats).

Особенности:
- используется потоковый парсинг и fallback-извлечение текста;
- геокодинг с кешом и фильтрацией нерелевантных адресов;
- адреса/owner/object очищаются от шумовых артефактов;
- данные сохраняются в PostgreSQL (`registry_records`, `geocode_cache`, `registry_cache_meta`).

## Поиск

- endpoint: `POST /api/v1/objects/search`;
- при выборе точки на карте выдаются только объекты, которые принимают отходы от других;
- по умолчанию показываются ближайшие 7;
- расстояние: road (OSRM) с fallback на air (Haversine).

## Полезные команды

```bash
# Логи
docker compose logs -f api
docker compose logs -f edge
docker compose logs -f cloudflared

# Миграции вручную (если нужно)
docker compose exec api python -m alembic upgrade head

# Пересборка только web
docker compose build --no-cache web
docker compose up -d web edge
```

## Очистка и обслуживание

Скрипт в корне:
- `docker-reset-and-up.ps1`

Примеры:

```powershell
# безопасная очистка + запуск
powershell -ExecutionPolicy Bypass -File .\docker-reset-and-up.ps1

# глубокая очистка (включая volumes) + запуск
powershell -ExecutionPolicy Bypass -File .\docker-reset-and-up.ps1 -Deep

# без пересборки
powershell -ExecutionPolicy Bypass -File .\docker-reset-and-up.ps1 -NoBuild

# запуск с quick tunnel профилем
powershell -ExecutionPolicy Bypass -File .\docker-reset-and-up.ps1 -Profile tunnel
```

> `-Deep` удаляет volumes (включая БД) — используйте только осознанно.

## Локальная разработка (без Docker)

### Backend

```bash
cd server
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend

```bash
cd web
npm install
npm run dev
```

## Тесты и качество

Backend:

```bash
cd server
$env:PYTHONPATH='.'
python -m pytest -q
```

Frontend:

```bash
cd web
npm run test
npm run lint
```

## Основные API маршруты

- `GET /health`
- `POST /api/v1/registry/import`
- `GET /api/v1/registry/import/{job_id}`
- `GET /api/v1/registry/cache`
- `DELETE /api/v1/registry/cache`
- `POST /api/v1/objects/search`
- `GET /api/v1/geocode/reverse`

## Troubleshooting

- **Ссылка tunnel не открывается**: перезапустите `cloudflared`, проверьте свежий URL в логах.
- **Пустая выдача в поиске**: убедитесь, что кэш реестра загружен (`/api/v1/registry/cache`).
- **Долгий импорт**: это нормально для больших PDF; следите за статусом `job_id` и метриками.
- **Порт занят**: поменяйте `HTTP_PORT` в `.env`.

## Лицензии и источники данных

- Карта: [OpenStreetMap](https://www.openstreetmap.org/copyright)
- Геокодинг: [Nominatim](https://operations.osmfoundation.org/policies/nominatim/)
- Маршрутизация: [OSRM](https://project-osrm.org/)
- Источник реестров: [ecoinfo.by](https://www.ecoinfo.by/)
