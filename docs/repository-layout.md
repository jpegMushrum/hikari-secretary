# Структура репозитория и сервисов

Корневой репозиторий `hikari-secretary` — точка сборки всей платформы. Его
`origin` остаётся неизменным. Внутри него будут находиться три Git-сабмодуля:

```text
hikari-secretary/
├── bot/                         # hikari-secretary-bot
├── backend/                     # hikari-secretary-backend
├── miniapp/                     # hikari-secretary-miniapp
├── deploy/                      # production-конфигурация и инструкции
├── docs/                        # общая документация платформы
├── docker-compose.yml           # полный интеграционный стек
├── .github/workflows/           # интеграционный CI/CD
└── .gitmodules
```

Все три каталога уже подключены как Git-сабмодули. `bot/` содержит стабильную
версию Python-бота, `backend/` — Go-сервис `v0.3.0-dev` с PostgreSQL, Bot API,
импортом первого доменного среза и проверкой Telegram-доступа, а
`miniapp/` готов к разработке административного интерфейса. Обновление каждого
компонента фиксируется в корне отдельным gitlink-коммитом.

## Ответственность компонентов

| Компонент | Репозиторий | Ответственность |
| --- | --- | --- |
| `bot/` | `hikari-secretary-bot` | Python/aiogram-адаптер Telegram, временный пользовательский UI и delivery worker |
| `backend/` | `hikari-secretary-backend` | Go API, PostgreSQL, миграции, бизнес-правила, outbox и авторизация Mini App / bot adapter |
| `miniapp/` | `hikari-secretary-miniapp` | Интерфейс администраторов внутри Telegram |

После миграции Go-бэкенд станет единственным владельцем PostgreSQL. Бот и Mini
App будут работать с ним через API; прямой доступ к базе из этих компонентов не
допускается.

## Docker Compose

Один `docker-compose.yml` в корне собирает и запускает доступный интеграционный
стек:

```text
postgres → migrations → importer → backend → bot
```

Mini App будет добавлен в эту схему после реализации. Сейчас Compose собирает
образы из `./bot` и `./backend`, применяет обе миграции, выполняет идемпотентный
импорт SQLite и запускает bot только после успешной готовности backend.

Не нужно запускать три независимых production Compose-стека: это создаст разные
сети, переменные окружения и неявные зависимости. Отдельные репозитории могут
иметь собственные Dockerfile, тесты и узкий Compose-файл только для локальных
интеграционных тестов — например, backend вместе с временным PostgreSQL.

Корневой Compose требует `backend/.env`, корневой `.env` и `targets.json`.
Примеры конфигурации находятся в соответствующих каталогах. Для запуска:

```bash
docker compose up -d --build --remove-orphans
```

Рабочая конфигурация и SQLite-данные остаются в корне, а интеграционный Compose
использует их через `BOT_ENV_FILE`, `BOT_TARGETS_FILE` и `BOT_DATA_DIR`.
Отдельный `bot/docker-compose.yml` используется только для автономной
разработки bot.

## Порядок перехода

1. ✅ Выделить историю бота, создать репозитории backend и Mini App, подключить
   их сабмодулями в пути `bot/`, `backend/` и `miniapp/`.
2. ✅ Создать backend foundation: PostgreSQL, миграции, healthcheck и Docker
   Compose для автономной разработки.
3. ✅ Добавить проверку Telegram Mini App `initData` и временный allowlist
   администраторов для всех административных API.
4. ✅ Зафиксировать целевую архитектуру, каталог use cases и модель первого
   доменного среза.
5. ✅ Реализовать закрытый Bot API, модель `People + Events + Registrations +
   Attendance + Feedback`, миграции PostgreSQL и проверяемый importer SQLite.
6. ✅ Добавить режим backend в bot: первый срез маршрутизируется в Go API,
   публикации и AI пока остаются совместимы с SQLite.
7. Реализовать административный Mini App поверх утверждённого API.
8. Перенести Publishing, а затем Learning Content; доставка остаётся только в
   Telegram.
9. ✅ Заменить заглушку корневого Compose интеграционным стеком backend + bot.
10. Добавить CI/CD: проверки сервисов в их репозиториях и интеграционный deploy из
   корня.
