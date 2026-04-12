# Фронт на Vercel / Netlify + API на своём ПК

Сайт на **Vercel** или **Netlify** открывается по **HTTPS**. Запросы к API идут на URL из `NEXT_PUBLIC_API_URL`. Браузер хранит JWT в **HttpOnly cookie на домене API**, поэтому фронт и API должны быть настроены под **кросс-домен** (CORS + `SameSite=None` + **HTTPS у API**).

## Важно

1. **Только ваш компьютер**  
   Если в `NEXT_PUBLIC_API_URL` указать `http://127.0.0.1:8000`, сайт на Vercel будет стучаться в **localhost посетителя**, а не в ваш ПК. Чтобы работало у вас (и у других), API нужно вынести в интернет, например:
   - [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/) (`cloudflared tunnel`)
   - [ngrok](https://ngrok.com/) и т.п.

2. **HTTPS у API**  
   Cookie сессии с `SameSite=None` требует флаг **Secure** → API должен отдаваться по **https://** (типичный туннель это даёт). Чистый `http://` на домашнем IP без TLS с фронтом на Vercel **не подойдёт** для входа по cookie.

3. **Корень репозитория**  
   В настройках Vercel / Netlify укажите **Root Directory** = `web` (папка с Next.js).

## Git и утечки данных

- В репозиторий **не попадают** файлы из **корневого `.gitignore`**: все `.env*`, кроме явно добавляемых шаблонов `*.example`, файл **`auth_users.json`** (пароли пользователей), локальные кэши с персональными запросами к геокодеру и т.п.
- **Секреты** (`JWT_SECRET`, пароль bootstrap, URL API с токеном туннеля) задавайте **только** в переменных окружения на Vercel/Netlify и в локальном `server/.env`, который **не коммитится**.
- Если какой‑то секретный файл уже был закоммичен раньше, одного `.gitignore` мало: удалите его из истории (`git rm --cached <путь>`) и при необходимости смените утёкшие пароли/ключи.

## Переменные на Vercel / Netlify

В панели проекта → Environment Variables:

| Переменная | Пример |
|------------|--------|
| `NEXT_PUBLIC_API_URL` | `https://ваш-туннель.example.com` (без слэша в конце) |

Пересоберите деплой после изменения переменных.

## Переменные локального API (`.env` в `server/`)

```env
# Точный origin фронта (через запятую, без пробелов вокруг)
CORS_ORIGINS=https://your-app.vercel.app,https://your-app.netlify.app

# Кросс-сайтовая cookie (фронт на другом домене)
AUTH_COOKIE_SAMESITE=none
AUTH_COOKIE_SECURE=1

JWT_SECRET=длинный-случайный-секрет
```

Для **только локальной разработки** (Next и API оба на localhost) можно не задавать `AUTH_COOKIE_SAMESITE` / `AUTH_COOKIE_SECURE` — останутся значения по умолчанию (`lax`, без Secure).

## Проверка

1. Запустите API: из каталога `server` (как у вас принято, например `uvicorn`).
2. Поднимите туннель на порт API и скопируйте **https**-URL в `NEXT_PUBLIC_API_URL`.
3. Откройте задеплоенный сайт → регистрация/вход → запросы в Network должны идти на туннель, ответ логина — `Set-Cookie` с `SameSite=None; Secure`.

## Netlify

В репозитории есть `web/netlify.toml` с плагином Next.js. При первом деплое Netlify подхватит сборку из `web`, если root задан верно.

## Vercel

Фреймворк Next.js определяется автоматически; при необходимости используйте `web/vercel.json`.
