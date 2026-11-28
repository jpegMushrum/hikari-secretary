# Структура репозитория и сервисов

Корневой репозиторий объединяет три Git-сабмодуля и фиксирует совместимые
коммиты компонентов. Версии перечислены в [README](../README.md),
выпуски — в [истории платформы](../CHANGELOG.md).

| Каталог | Что в нём |
| --- | --- |
| [bot](https://github.com/jpegMushrum/hikari-secretary-bot) | Python/aiogram. Диалоги участников и администраторов, приём сообщений, доставка в Telegram. |
| [backend](https://github.com/jpegMushrum/hikari-secretary-backend) | Go. Закрытый API бота, Admin API и Member API, бизнес-правила, PostgreSQL, миграции и отдельный импортёр SQLite. |
| [miniapp](https://github.com/jpegMushrum/hikari-secretary-miniapp) | React/TypeScript. Режимы администратора и участника в Telegram, локальный браузерный вход для разработки. |
| `deploy/` | Конфигурация production nginx, скрипты развёртывания и снимка SQLite, проверки. |
| `.github/workflows/` | Интеграционные проверки зафиксированных сабмодулей и ручное развёртывание production из `main`. |
| `docs/` | Архитектура, планы, руководства по эксплуатации. |

В рабочем стеке только backend обращается к PostgreSQL. Бот и miniapp
пользуются разными API. Новые изображения анонсов бот загружает через
backend. Backend выдаёт их с авторизацией из локального каталога либо
из приватного S3. Общий каталог поддерживает исторические вложения.

## Разработка и развёртывание

После клонирования или обновления корня выполните
`git submodule update --init --recursive`, чтобы получить зафиксированные
версии компонентов. Изменения компонента публикуются сначала в его репозитории,
затем корень фиксирует новый коммит сабмодуля.

| Compose-файл в корне | Назначение |
| --- | --- |
| `docker-compose.production.yml` | PostgreSQL, миграции, backend, бот и miniapp через nginx с HTTPS. Для первого перехода со старой установки есть ручной профиль `legacy-import`. [Руководство](production.md) |
| `docker-compose.bot-local.yml` | Локальный PostgreSQL, backend, браузерный вход через dev gateway и miniapp. Полный запуск также включает тестового бота с доставкой в Telegram. [Локальный запуск](https://github.com/jpegMushrum/hikari-secretary-miniapp/blob/main/README.md) |

CI корневого репозитория проверяет компоненты на коммитах, зафиксированных
в проверяемом коммите платформы. Production получает образы из GHCR по digest.
Подготовку GitHub Actions и VPS описывает [руководство production](production.md).
Развитие административного интерфейса и режима участника описано
в [roadmap платформы](roadmap.md).
