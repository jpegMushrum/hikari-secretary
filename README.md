# Hikari Secretary

![Статус](https://img.shields.io/badge/status-restructuring-F59E0B)
![Compose](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)

Интеграционный репозиторий платформы клуба японского языка **Hikari ITMO**.
Он объединит Telegram-бота для участников, Go-бэкенд и Telegram Mini App для
администраторов.

[Канал Hikari ITMO](https://t.me/Hikari_ITMO) · [Telegram-бот](https://t.me/hikari_secretary_bot)

## Статус перехода

Все три компонента уже подключены как Git-сабмодули. Рабочий Telegram-бот
**v0.9.0** находится в [`bot/`](bot/README.md); backend перешёл в технический
релиз `v0.3.0-dev` с первым рабочим Bot API и импортом первого доменного среза;
Mini App имеет первую браузерную версию с отдельным локальным стендом.

| Компонент | Будущий репозиторий | Состояние |
| --- | --- | --- |
| `bot/` | `hikari-secretary-bot` | Стабильный участнический интерфейс v0.9.0 |
| `backend/` | `hikari-secretary-backend` | Go v0.3.0-dev: PostgreSQL, Bot API, миграции и первый доменный срез |
| `miniapp/` | `hikari-secretary-miniapp` | Первая браузерная версия: мероприятия, участники, ИИ, отзывы |

## Два режима запуска

Все команды выполняются из корня интеграционного репозитория. Файлы
самостоятельные, объединять их через несколько `-f` не нужно.

| Файл | Назначение |
| --- | --- |
| `docker-compose.production.yml` | Сервер: PostgreSQL, снимок SQLite, миграции, импорт, backend, бот и miniapp с HTTPS на 8443/880 |
| `docker-compose.bot-local.yml` | Локальная проверка: PostgreSQL, backend, тестовый бот и miniapp на localhost:5173 с браузерным входом |

```powershell
# Локально; .env содержит токен тестового бота
 docker compose -f docker-compose.bot-local.yml up -d --build
```

Локальная база — подготовленная копия импорта, выбирается через
`LOCAL_DATABASE_NAME`. Имя проекта и volumes сохранены. Бот действительно
отправляет публикации; отдельного demo seed больше нет.
Подробности: [miniapp/README.md](miniapp/README.md).

```sh
# Сервер, после подготовки сертификата и перехода с SQLite
 docker compose -f docker-compose.production.yml up -d --build
```

Серверные `.env`, `backend/.env`, `targets.json` и `data/` сохраняются отдельно.
Порядок переноса, проверки очередей и отката: [docs/production.md](docs/production.md).
Примеры настроек: [.env.example](.env.example), [backend/.env.example](backend/.env.example).
Обычный `docker compose up` без `-f` больше не используется.

## Документация

- [Структура репозитория и план перехода](docs/repository-layout.md)
- [Целевая архитектура платформы](docs/architecture.md)
- [Каталог use cases](docs/use-cases.md)
- [Модель данных и план переноса](docs/domain-model.md)
- [Документация текущего бота v0.9.0](bot/docs/README.md)
- [Документация backend v0.3.0-dev](backend/README.md)
- [История изменений бота](bot/CHANGELOG.md)

## Безопасность данных

Не добавляйте в Git `.env`, `targets.json` и `data/`. В них находятся токены,
идентификаторы Telegram и персональные данные участников. При переносе бота в
отдельный репозиторий рабочие конфигурация и база должны быть перенесены на
сервере отдельно, безопасным способом.
