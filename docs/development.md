# Для команды: разработка

Рабочие заметки команды: кто за что отвечает, как поднять проект для разработки, правила работы. Описание решения для проверки — в [README](../README.md).

## Кто что делает

| Кто | Зона файлов | Задачи | Ветка |
|---|---|---|---|
| Толик | `backend/apps/core/`, `backend/apps/api/`, `deploy/`, Docker, документация | [docs/tasks/tolik.md](tasks/tolik.md) | `feature/core` |
| Яша | `backend/apps/bot/` | [docs/tasks/yasha.md](tasks/yasha.md) | `feature/bot` |
| Максим | `frontend/` | [docs/tasks/maxim.md](tasks/maxim.md) | `feature/miniapp` |

Зоны не пересекаются, поэтому работать можно параллельно. Правки в чужой зоне не делаем:
пишем владельцу зоны. Модели и миграции ведёт только Толик.

ИИ-ассистент (Claude Code или Codex) читает `CLAUDE.md` и `AGENTS.md` сам. Достаточно
написать ему «Я Яша» — он откроет нужный файл задач и предложит, с чего начать.

## Быстрый старт

Нужны Python 3.13 (зависимости зафиксированы под него) и Node 22. Токен бота у капитана команды: в git, в код и в чаты его не отправлять.

```powershell
git clone https://github.com/Shipovmax/hackathon_max.git
cd hackathon_max
copy .env.example .env               # затем вписать BOT_TOKEN
cd backend
py -3.13 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py test                # тесты должны проходить
python manage.py createsuperuser     # для входа в админку
python manage.py runserver           # API и админка: http://localhost:8000/admin/
```

Демо-данные (тестовая сеть, сотрудники, график, задачи на сегодня):

```powershell
python manage.py seed_demo --owner-max-id <ваш MAX id>
```

Команда печатает коды приглашения — их отправляют боту, чтобы привязать сотрудника. Повторный запуск безопасен, `--reset` очищает прежние демо-данные. Свой MAX id можно взять из логов бота или указать любой: аккаунт создастся и станет владельцем.

Бот и планировщик запускаются в отдельных терминалах (в том же venv):

```powershell
python manage.py run_bot             # получает события MAX (Long Polling)
python manage.py run_scheduler       # напоминания, просрочки, эскалации
```

С одним токеном `run_bot` должен работать **только у одного человека одновременно**: параллельные Long Polling перехватывают события друг у друга. Бот работает на сервере, поэтому перед локальной отладкой его останавливают (`docker compose stop bot` на сервере) и потом возвращают.

Мини-приложение (отдельный терминал):

```powershell
cd frontend
npm ci
copy .env.example .env               # VITE_USE_MOCKS=1: экраны на демо-данных, бэкенд не нужен
npm run dev                          # http://localhost:5173
```

Чтобы фронтенд работал с реальным API, в `frontend/.env` поставьте `VITE_USE_MOCKS=0`. Запросы `/api` проксируются на `localhost:8000`, но реальный API отвечает только внутри MAX: он проверяет подпись запуска, поэтому в обычном браузере вы увидите заглушку «Откройте приложение из чата с ботом».

Проверка перед пушем: `python manage.py test` в `backend` и `npm run build` в `frontend`.

**Локально тесты идут на SQLite, а на сервере работает PostgreSQL, и он строже.** Так мы уже
пропустили поломку: `select_for_update()` вместе с `select_related` по необязательной связи
даёт `FOR UPDATE` поверх outer join — SQLite это молча пропускает, PostgreSQL отвечает
`NotSupportedError`. Поэтому блокирующие запросы пишем как `select_for_update(of=("self",))`,
а перед сдачей и после заметных изменений в запросах прогоняем тесты на настоящей базе:

```bash
docker compose run --rm --no-deps migrate python manage.py test --noinput
```

## Карта кода и статус

| Где | Что делает | Статус |
|---|---|---|
| `backend/apps/core/models/` | 8 сущностей, миграции `0001`–`0009` | готово |
| `backend/apps/core/management/commands/seed_demo.py` | загружает тестовые данные из `backend/testdata/demo_network.json` | готово, есть тесты |
| `backend/apps/core/domain/permissions.py` | `check_can_mark`: право на отметку по смене, с причиной отказа | готово, есть тесты |
| `backend/apps/core/domain/coverage.py` | `find_gaps`: незакрытые окна графика с допуском на границах | готово, есть тесты |
| `backend/apps/core/domain/lifecycle.py`, `day.py` | плановое время, статус задачи, `mark_done`, создание задач дня | готово, есть тесты |
| `backend/apps/api/auth.py` | проверка подписи MAX и вход владельца (403 `not_owner` для остальных) | готово, есть тесты |
| `backend/apps/api/views/`, `urls.py`, `presenters.py`, `scoping.py` | все эндпоинты мини-приложения, проверка владения сетью, валидация | готово, есть тесты |
| `backend/apps/bot/max_api/client.py` | клиент MAX API: `get_me`, `get_updates`, `send_message`, `answer_callback`, `download_file` | готово |
| `backend/apps/bot/handlers/onboarding.py` | `/start`, выбор роли, `/role`, привязка сотрудника по коду | готово, есть тесты |
| `backend/apps/bot/handlers/tasks.py` | «Выполнено», фото, «Беру», «что осталось» | готово, есть тесты |
| `backend/apps/bot/scheduler.py` | 9 задач планировщика, цикл в `run_scheduler` | готово, есть тесты |
| `backend/apps/bot/notifications.py` | 3 уведомления владельцу с диплинком в карточку точки | готово, есть тесты |
| `backend/apps/bot/texts.py`, `keyboards.py` | формулировки сообщений и кнопки | готово |
| `frontend/src/screens/` | 5 экранов владельца с редактированием | готово; на демо-данных (`VITE_USE_MOCKS=1`) и с настоящим API |
| `Dockerfile`, `compose.yaml`, `deploy/` | сборка и запуск | проверено на сервере: сборка около 75 секунд, все сервисы поднимаются, https работает |
| README, `openapi.yaml`, `DATA-API.yaml` | материалы для сдачи | готово; DATA-API проходит валидатор организаторов |

Бот и планировщик реализованы полностью: заглушек `NotImplementedError` в `apps/bot/` не осталось.

## Как проверить бота вручную

Проще всего залить демо-данные командой `seed_demo` (см. выше): она создаёт точки, сотрудников с кодами приглашения, график и задачи. Владельцем становится указанный MAX id. Точки, сотрудников и график можно вести и в самом мини-приложении.

1. Запустите `run_bot`, откройте бота в MAX, отправьте `/start` и нажмите «Я владелец». Создастся сеть «Моя сеть».
2. Выполните `python manage.py seed_demo --owner-max-id <ваш MAX id>` — она напечатает коды приглашения. Либо добавьте точку и сотрудника в мини-приложении, код покажется рядом с сотрудником.
3. В MAX отправьте боту `/role`, нажмите «Я сотрудник» и пришлите код. Бот ответит «Готово. Вы подключены к точке …».

Один аккаунт MAX может быть и владельцем, и сотрудником: роль переключается командой `/role`.

## Контракт API мини-приложения

Авторизация: заголовок `X-Max-Init-Data` со значением `window.WebApp.initData`. Формы ответов описаны в [frontend/src/api/types.ts](../frontend/src/api/types.ts).

| Эндпоинт | Экран | Статус |
|---|---|---|
| `GET /api/health/` | проверка сервера | готово |
| `GET /api/me/` | вход, роль, сеть | готово |
| `GET /api/dashboard/?date=` | Сводка: точки с проблемами сверху | готово |
| `GET /api/stores/{id}/day/?date=` | Карточка точки: задачи дня, кто отметил, кто на смене | готово |
| `GET/POST /api/stores/`, `GET/PATCH /api/stores/{id}/` | Точки и сотрудники: часы работы и выходные (`closed_weekdays`, 0 — пн) меняются после создания | готово |
| `POST /api/stores/{id}/employees/`, `POST /api/employees/{id}/invite/`, `POST /api/employees/{id}/dismiss/` | код приглашения, увольнение (история остаётся) | готово |
| `GET/POST /api/stores/{id}/task-templates/`, `PATCH/DELETE /api/task-templates/{id}/` | Задачи точки: плановое время, `available_from` (раньше него не отметить, по умолчанию на 30 минут раньше плана), допуск, фото, «Беру». Удаление скрывает задачу, история остаётся | готово |
| `GET/PUT /api/stores/{id}/schedule/?week=` | График: чтение и сохранение (опубликованная неделя остаётся опубликованной) | готово |
| `POST /api/stores/{id}/schedule/coverage/` | проверка покрытия черновика без сохранения | готово |
| `POST /api/stores/{id}/schedule/publish/` | публикация недели | готово |
| `GET /api/completions/{id}/photo/` | фото отметки, только владельцу этой сети | готово |
| `/api/network/` | переименование сети | 501, фронтенд его не вызывает |

Ошибки приходят как `{"detail": "текст"}`: 400 для неверных данных, 404 для чужих или несуществующих объектов, 409 для действий, которые сейчас невозможны.

## Правила работы

- Секреты только в `.env` (он в `.gitignore`). Рабочий токен в репозиторий попасть не должен: за это снимают баллы.
- Изменили модели: `python manage.py makemigrations core` и добавьте файл миграции в коммит. При конфликте номеров пересоздайте свою миграцию.
- Версии зависимостей не меняем без причины. Если меняли, обновите `requirements.txt` или `package-lock.json`.
- Не реализуем то, что в «Won't have» (список в CLAUDE.md, раздел 10).
- Коммиты и имена в коде пишем на английском.
