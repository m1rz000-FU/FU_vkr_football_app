# Статистика РПЛ

Веб-приложение **«Статистика РПЛ»**: матчи РПЛ (live и по дням), турнирная таблица, детальная статистика матча и профиль с любимой командой. В браузере вкладка называется **«Статистика РПЛ»** (`football-stats/index.html`).

## Состав репозитория

| Путь | Назначение |
|------|------------|
| `football-stats/` | Фронтенд: **React 19**, **Vite 6**, **React Router**, **Framer Motion**, `axios` |
| `app.py` | **Flask** на порту **5001**: прокси к [LiveScore API](https://www.live-score-api.com/) |
| `livescore_api.py` | Клиент LiveScore, маршруты вида `/api/livescore/rpl/*` |
| `requirements.txt` | Зависимости Python для прокси |
| `scripts/curl_livescore_rpl.sh` | Пример curl к API и к локальному Flask |
| `scripts/dev-lan.sh` | Одновременный запуск Flask и Vite для отладки по LAN |
| `docs/` | Android setup, правила по лимитам API |
| `.github/workflows/deploy-pages.yml` | **GitHub Actions**: сборка фронта и деплой на **GitHub Pages** |

Корневой `.env` или `football-stats/.env` (и локальные `*.local.env`, не в git): ключи **`LIVESCORE_API_KEY`**, **`LIVESCORE_API_SECRET`**.

## Функции фронтенда (кратко)

- **Live / Игры** — список матчей, выбор даты, переход к статистике матча.
- **Таблица** — турнирная таблица РПЛ, параметр `?team=` для фокуса на строке.
- **Статистика матча** — показатели с API (при наличии id матча), заголовок вкладки: `Хозяева — Гости · Статистика РПЛ`.
- **Профиль** — любимая команда (локальный «аккаунт»), обзор из таблицы + календарь; карточки матчей: соперник, дата/время, **Дома** (иконка дома) / **В гостях** (контурный самолёт).
- **Профиль → аккаунт** — имя, вход/регистрация (локально в `localStorage`).

Запросы к API идут через **`football-stats/src/services/api.js`**: кэш, TTL, дедупликация (см. `.cursor/rules/minimize-api-requests.mdc`).

## Запуск локально

### 1. Прокси (Flask)

Из **корня** репозитория:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

Сервер слушает **http://127.0.0.1:5001**.

### 2. Фронтенд (Vite)

```bash
cd football-stats
npm ci
npm run dev
```

По умолчанию **http://localhost:5173**. В `vite.config.js` настроен прокси **`/api` → `http://127.0.0.1:5001`**, чтобы фронт ходил к Flask без CORS.

## Сборка

```bash
cd football-stats
npm run build
```

Результат в `football-stats/dist/`. Каталоги `dist/` и кэш Vite не коммитятся (`.gitignore`).

## Проверка API

```bash
./scripts/curl_livescore_rpl.sh
```

(при необходимости поправьте URL и ключи под свою среду.)

## Деплой на GitHub Pages (CI)

Workflow **`.github/workflows/deploy-pages.yml`**:

- **Триггеры:** push в ветку **`main`**, ручной запуск **Actions → Deploy GitHub Pages → Run workflow**.
- **Шаги:** `checkout` → Node 20 + `npm ci` в `football-stats/` → `npm run build` → загрузка **`football-stats/dist`** как артефакт Pages → `deploy-pages`.

**Что настроить в репозитории GitHub**

1. **Settings → Pages**: источник **GitHub Actions** (не «Deploy from branch» для этого workflow).
2. Ветка по умолчанию для пушей — **`main`**, иначе поправьте `on.push.branches` в YAML.
3. Первый деплой после включения Pages может занять 1–2 минуты; URL будет вида `https://<user>.github.io/<repo>/`.

Секреты LiveScore на Pages: фронт обычно собирается **без** секретов в репозитории; ключи либо в **GitHub Secrets** и подстановка на этапе сборки (если добавите шаг), либо отдельный бэкенд. Текущий workflow **только** собирает статический `dist` — для работы API в проде нужен доступный прокси или переменные среды по вашей схеме.

## Полезные ссылки внутри проекта

- Подробности по фронту и скриптам: [`football-stats/README.md`](football-stats/README.md)
- Сборка Android (Capacitor): [`docs/ANDROID_SETUP.md`](docs/ANDROID_SETUP.md)
- Экономия запросов к внешнему API: [`docs/minimize-api-requests.md`](docs/minimize-api-requests.md)
