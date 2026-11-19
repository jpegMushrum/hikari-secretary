# 光 · Hikari Secretary

![Статус: работает](https://img.shields.io/badge/status-running-2EA44F)
[![Bot: последний описанный релиз 0.9.0](https://img.shields.io/badge/bot-0.9.0-5865F2)](https://github.com/jpegMushrum/hikari-secretary-bot/blob/main/CHANGELOG.md)
[![Backend: 0.3.2](https://img.shields.io/badge/backend-0.3.2-00ADD8)](https://github.com/jpegMushrum/hikari-secretary-backend/blob/main/README.md)
[![Miniapp: 0.1.2](https://img.shields.io/badge/miniapp-0.1.2-61DAFB)](https://github.com/jpegMushrum/hikari-secretary-miniapp/blob/main/README.md)

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Go](https://img.shields.io/badge/Go-1.27-00ADD8?logo=go&logoColor=white)
![React](https://img.shields.io/badge/React-19-149ECA?logo=react&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-18-4169E1?logo=postgresql&logoColor=white)
![Docker Compose](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)

Платформа клуба японского языка **Hikari ITMO**: встречи, участники,
публикации и обратная связь. Основное направление — статистика посещений
и помощь организаторам клуба.

[Канал клуба](https://t.me/Hikari_ITMO) ·
[Telegram-бот](https://t.me/hikari_secretary_bot) ·
[Документация](docs/README.md) ·
[История релизов](CHANGELOG.md) ·
[Планы развития](docs/miniapp-plan.md)

## Возможности

**Для участников:** регистрация на мероприятия, отмена записи, профиль,
напоминания, подтверждение посещения и отзывы — через Telegram-бота.

**Для организаторов:**

- Мероприятия, списки участников, посещаемость и статистика.
- Публикации в каналы, чаты и топики: текст, фотографии, альбомы и rich messages.
- Черновики из сообщений боту, предпросмотр и настройка публикации в miniapp.
- Отложенные отправки, отзывы и настраиваемые таблицы.
- ИИ-материалы для разговорного клуба при подключённом сервисе генерации.

Miniapp пока доступен только администраторам. Управление через бота
сохраняется: сообщение готовится в Telegram, дальнейшую настройку можно
продолжить в чате или в панели.

## Состояние и версии

Бот и административная miniapp работают через Go backend с PostgreSQL.
SQLite используется только для ручного переноса со старой установки.
Ближайшие задачи — проверка полных сценариев,
исправление ошибок и упрощение интерфейса.

Этот репозиторий — основная точка входа и сборки всей платформы.
Компоненты подключены как Git-сабмодули; состав сборки фиксируется их
коммитами в корневом репозитории.

| Компонент | Версия, указанная в проекте | Назначение |
| --- | --- | --- |
| [Бот](https://github.com/jpegMushrum/hikari-secretary-bot/blob/main/README.md) | `0.9.0` | Telegram-интерфейс и доставка сообщений |
| [Backend](https://github.com/jpegMushrum/hikari-secretary-backend/blob/main/README.md) | `0.3.2` | Бизнес-логика, API, авторизация и PostgreSQL |
| [Miniapp](https://github.com/jpegMushrum/hikari-secretary-miniapp/blob/main/README.md) | `0.1.2` | Административная панель на React и TypeScript |

Эти номера относятся к компонентам. Отдельная версия общего релиза платформы
пока не назначена. Релизы backend, miniapp и изменения интеграции описаны
в [общей истории платформы](CHANGELOG.md).

В этот релиз входят **Backend 0.3.2** и **Miniapp 0.1.2**.
Обновляйте их вместе, чтобы сортировка по любой колонке работала для всего
отфильтрованного списка.

## Запуск

Из корня проекта, после настройки выбранного окружения:

```sh
# Локальная проверка с тестовым ботом
docker compose -f docker-compose.bot-local.yml up -d --build

# Только браузерная панель с локальным API
docker compose -f docker-compose.bot-local.yml up -d --build miniapp

# Production
docker compose -f docker-compose.production.yml up -d --build
```

Это два самостоятельных стека. Локальный открывает miniapp на
`localhost:5173`; production использует HTTPS с настраиваемыми портами.
Обычный production-запуск применяет миграции PostgreSQL. Для первого
переноса SQLite отдельно запустите сервисы профиля `legacy-import`
до запуска приложения.

Перед первым запуском: [локальное окружение](https://github.com/jpegMushrum/hikari-secretary-miniapp/blob/main/README.md) или
[production, сертификат и перенос SQLite → PostgreSQL](docs/production.md).
Для production заполните корневой `.env`, `backend/.env` и `targets.json`.
Локальный стек берёт настройки backend из Compose. Для первого запуска
на пустом локальном томе задайте `LOCAL_DATABASE_NAME=hikari_dev` в корневом
`.env`. Чтобы увидеть импортированные данные, укажите имя уже восстановленной
локальной базы. Цели тестового бота задаются в корневом `targets.json`.

## Документация

- [Участникам клуба](https://github.com/jpegMushrum/hikari-secretary-bot/blob/main/docs/participant-guide.md)
- [Администраторам](https://github.com/jpegMushrum/hikari-secretary-bot/blob/main/docs/admin-guide.md)
- [Черновики и miniapp](https://github.com/jpegMushrum/hikari-secretary-bot/blob/main/docs/miniapp-handoff.md)
- [Архитектура платформы](docs/architecture.md)
- [API backend](https://github.com/jpegMushrum/hikari-secretary-backend/blob/main/openapi/openapi.yaml)
- [Roadmap и приоритеты](docs/miniapp-plan.md)
- [Все руководства](docs/README.md)
