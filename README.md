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
релиз `v0.3.0-dev` с защищённым контуром Telegram-доступа и первым срезом
людей; Mini App пока
содержит стартовую документацию.

| Компонент | Будущий репозиторий | Состояние |
| --- | --- | --- |
| `bot/` | `hikari-secretary-bot` | Стабильный участнический интерфейс v0.9.0 |
| `backend/` | `hikari-secretary-backend` | Go v0.3.0-dev: PostgreSQL, миграции, Telegram-доступ и первый People API |
| `miniapp/` | `hikari-secretary-miniapp` | Будущий интерфейс администраторов |

Корневой [`docker-compose.yml`](docker-compose.yml) — валидная интеграционная
заглушка. Он **не запускает приложение и не предназначен для deploy**, пока не
будут подключены все три сабмодуля. Для текущего бота используйте инструкции в
[`bot/README.md`](bot/README.md).

До выделения бота в отдельный репозиторий его рабочие `.env`, `targets.json` и
`data/` остаются в корне. Поэтому текущий запуск выполняется из корня командой
`docker compose -f bot/docker-compose.yml up -d --build`; Compose передаёт эти
пути в `bot/` через настраиваемые переменные.

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
