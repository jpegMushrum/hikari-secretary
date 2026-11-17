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

Корневой [`docker-compose.yml`](docker-compose.yml) собирает backend и bot в
правильной последовательности: PostgreSQL → миграции → импорт SQLite →
backend → bot. Mini App пока не входит в production-стек; её отдельный
стенд запускается через `docker-compose.dev.yml`.

## Mini App локально

```powershell
docker compose -f docker-compose.dev.yml up -d --build
```

Открыть [localhost:5173](http://localhost:5173): тёмная тема, четыре
административных раздела и настоящие Go API/PostgreSQL с вымышленными
демоданными. Этот стенд не использует рабочие `.env`, SQLite и Telegram-бота.
Подробности и команды проверок — [miniapp/README.md](miniapp/README.md).

## Основной стек бота

Рабочие `.env`, `targets.json` и `data/` остаются в корне интеграционного
репозитория. Основной запуск выполняется корневым Compose; отдельный
`bot/docker-compose.yml` остаётся доступен для автономной разработки bot.

Примеры конфигурации разделены по сервисам: [.env.example](.env.example) для
текущего корневого запуска бота, [backend/.env.example](backend/.env.example)
для Go backend и [bot/.env.example](bot/.env.example) для самостоятельного
запуска bot. Рабочие `.env` не коммитятся.

Для интеграционного запуска скопируйте примеры, заполните секреты и создайте
рабочий файл целей публикации:

```powershell
Copy-Item .env.example .env
Copy-Item backend/.env.example backend/.env
Copy-Item bot/targets.example.json targets.json
docker compose up -d --build --remove-orphans
```

`BOT_SERVICE_TOKEN` в корневом `.env` и `backend/.env` должен совпадать.

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
