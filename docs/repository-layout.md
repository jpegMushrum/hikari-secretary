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
├── docker-compose.production.yml # серверный стек
├── docker-compose.bot-local.yml  # локальный тестовый стек
├── .github/workflows/           # интеграционный CI/CD
└── .gitmodules
```

Все три каталога уже подключены как Git-сабмодули. `bot/` содержит стабильную
версию Python-бота, `backend/` — Go-сервис `v0.3.0` с PostgreSQL, Bot API,
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

Остались два самостоятельных файла в корне: `docker-compose.production.yml`
и `docker-compose.bot-local.yml`. Первый обслуживает production и переход
с SQLite, второй — локальный backend, miniapp и тестового бота.
Оба содержат необходимые зависимости; дополнительных overlay нет.
Имена проектов и volumes сохранены. Отдельный Compose backend и демостенд
удалены; при необходимости можно запускать выбранные сервисы локального файла.
Инструкции: [production](production.md), [локальная разработка](https://github.com/jpegMushrum/hikari-secretary-miniapp/blob/main/README.md).

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
