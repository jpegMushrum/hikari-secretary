# Структура репозитория и сервисов

Корневой репозиторий объединяет три Git-сабмодуля и фиксирует совместимые
коммиты компонентов. Версии перечислены в [README](../README.md),
выпуски — в [истории платформы](../CHANGELOG.md).

| Каталог | Что в нём |
| --- | --- |
| [bot](https://github.com/jpegMushrum/hikari-secretary-bot) | Python/aiogram. Диалоги участников и администраторов, приём сообщений, доставка в Telegram. |
| [backend](https://github.com/jpegMushrum/hikari-secretary-backend) | Go. Закрытый API бота, Admin API, бизнес-правила, PostgreSQL, миграции и отдельный импортёр SQLite. |
| [miniapp](https://github.com/jpegMushrum/hikari-secretary-miniapp) | React/TypeScript. Административная панель Telegram и локальный браузерный режим для разработки. |
| `deploy/` | Конфигурация production nginx, скрипт снимка SQLite и проверки развёртывания. |
| `docs/` | Архитектура, планы, руководства по эксплуатации. |

В рабочем стеке только backend обращается к PostgreSQL. Бот и miniapp
пользуются разными API. Бот сохраняет файлы медиа в общем каталоге,
из которого backend читает их для предпросмотра.

## Разработка и развёртывание

После клонирования или обновления корня выполните
`git submodule update --init --recursive`, чтобы получить зафиксированные
версии компонентов. Изменения компонента публикуются сначала в его репозитории,
затем корень фиксирует новый коммит сабмодуля.

| Compose-файл в корне | Назначение |
| --- | --- |
| `docker-compose.production.yml` | PostgreSQL, миграции, backend, бот и miniapp через nginx с HTTPS. Для первого перехода со старой установки есть ручной профиль `legacy-import`. [Руководство](production.md) |
| `docker-compose.bot-local.yml` | Локальный PostgreSQL, backend, браузерный вход через dev gateway и miniapp. Полный запуск также включает тестового бота с доставкой в Telegram. [Локальный запуск](https://github.com/jpegMushrum/hikari-secretary-miniapp/blob/main/README.md) |

Работающий административный интерфейс и планы пользовательского режима описаны
в [roadmap](miniapp-plan.md). Автоматизация CI/CD для интеграционного
развёртывания остаётся отдельной задачей.
