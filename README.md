# Hikari Secretary

![Статус](https://img.shields.io/badge/status-restructuring-F59E0B)
![Compose](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)

Интеграционный репозиторий платформы клуба японского языка **Hikari ITMO**.
Он объединит Telegram-бота для участников, Go-бэкенд и Telegram Mini App для
администраторов.

[Канал Hikari ITMO](https://t.me/Hikari_ITMO) · [Telegram-бот](https://t.me/hikari_secretary_bot)

## Статус перехода

Рабочий код Telegram-бота **v0.9.0** уже расположен в [`bot/`](bot/README.md).
Пока это обычный каталог в корневом репозитории: его предстоит выделить в
репозиторий `hikari-secretary-bot` и заменить Git-сабмодулем. Каталоги
`backend/` и `miniapp/` намеренно ещё не созданы — их добавит владелец после
создания соответствующих репозиториев.

| Компонент | Будущий репозиторий | Состояние |
| --- | --- | --- |
| `bot/` | `hikari-secretary-bot` | Исходный код v0.9.0 подготовлен к выделению |
| `backend/` | `hikari-secretary-backend` | Будущий Go API и владелец PostgreSQL |
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
- [Документация текущего бота v0.9.0](bot/docs/README.md)
- [История изменений бота](bot/CHANGELOG.md)

## Безопасность данных

Не добавляйте в Git `.env`, `targets.json` и `data/`. В них находятся токены,
идентификаторы Telegram и персональные данные участников. При переносе бота в
отдельный репозиторий рабочие конфигурация и база должны быть перенесены на
сервере отдельно, безопасным способом.
