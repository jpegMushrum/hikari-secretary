# 光 · Hikari Secretary

![Статус: работает](https://img.shields.io/badge/status-running-2EA44F)
[![Bot 1.0.2](https://img.shields.io/badge/bot-1.0.2-5865F2)](https://github.com/jpegMushrum/hikari-secretary-bot/blob/main/CHANGELOG.md)
[![Backend 0.5.0](https://img.shields.io/badge/backend-0.5.0-00ADD8)](https://github.com/jpegMushrum/hikari-secretary-backend/blob/main/README.md)
[![Miniapp 0.3.0](https://img.shields.io/badge/miniapp-0.3.0-61DAFB)](https://github.com/jpegMushrum/hikari-secretary-miniapp/blob/main/README.md)

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

**Для участников:** в Telegram-боте кнопка «Ближайшие мероприятия» показывает,
на какие встречи можно записаться и где уже есть запись. Из «Управления записью»
можно изменить напоминание или отменить участие. Если у встречи есть ссылка на
опубликованное сообщение, его можно открыть кнопкой «Анонс».
Анкета доступна в «Моём профиле».
Бот также принимает подтверждения посещения и отзывы.

**Для организаторов:**

- Публикации в каналы, чаты и топики: текст, фотографии, альбомы и rich messages.
- Черновики из новых и пересланных сообщений боту. После сохранения можно
  открыть черновик в miniapp или продолжить в чате с предпросмотром,
  регистрацией, выбором целей и времени отправки.
- Активные мероприятия, списки участников и очередь публикаций в Telegram.
  Архив мероприятий, отзывы, посещаемость и статистика в таблицах miniapp.
- Автоматическая подготовка материалов для разговорного клуба. В miniapp
  доступны история заданий, предпросмотр, статус публикации и ручная постановка
  новой генерации в очередь.

Кнопка «Панель клуба» открывает miniapp и для участников. Там доступны
мероприятия и анонсы, управление собственной записью, отметка посещения,
профиль и свои отзывы. Администраторы могут переключаться между двумя
режимами из бокового меню.

Для локальной проверки доступен «Тайный Санта»: запись с пожеланиями,
административная жеребьёвка, личные карточки получателей и пересмотр пар
при исключении участника.
[Сценарий проверки в браузере](docs/santa-testing.md).

На том же стенде доступны выборы маскота с подачей концептов, голосованием
и публикацией итогов. [Правила и сценарий проверки](docs/mascot-election.md).

## Состояние и версии

Бот и miniapp работают через Go backend с PostgreSQL.
SQLite используется только для ручного переноса со старой установки.
Бот 1.0.0 перешёл в сопровождение. В выпуск от 22 ноября 2026 года входят интерфейс
участника в Miniapp 0.2.0, его API в Backend 0.4.0 и вход из Бота 1.0.1.
Выпуск от 26 ноября 2026 года с Тайным Сантой и выборами маскота подготовлен
к развёртыванию.

Этот репозиторий — основная точка входа и сборки всей платформы.
Компоненты подключены как Git-сабмодули; состав сборки фиксируется их
коммитами в корневом репозитории.

| Компонент | Версия, указанная в проекте | Назначение |
| --- | --- | --- |
| [Бот](https://github.com/jpegMushrum/hikari-secretary-bot/blob/main/README.md) | `1.0.2` | Telegram-интерфейс и доставка сообщений |
| [Backend](https://github.com/jpegMushrum/hikari-secretary-backend/blob/main/README.md) | `0.5.0` | Бизнес-логика, API, авторизация и PostgreSQL |
| [Miniapp](https://github.com/jpegMushrum/hikari-secretary-miniapp/blob/main/README.md) | `0.3.0` | Интерфейсы участника и администратора на React и TypeScript |

Эти номера относятся к компонентам. Отдельная версия общего релиза платформы
пока не назначена. Релизы backend, miniapp и изменения интеграции описаны
в [общей истории платформы](CHANGELOG.md).

## Запуск

Из корня проекта, после настройки выбранного окружения:

```sh
# Локальная проверка с тестовым ботом
docker compose -f docker-compose.bot-local.yml up -d --build

# Только браузерная панель с локальным API
docker compose -f docker-compose.bot-local.yml up -d --build miniapp
```

Это два самостоятельных стека. Локальный открывает miniapp на
`localhost:5173`; production использует HTTPS с настраиваемыми портами.
Production обновляется по ручному запуску GitHub Actions из `main`
после настройки окружения `production`. Сервер загружает готовые образы из GHCR
по digest и применяет миграции PostgreSQL. Для первого переноса SQLite
отдельно запустите сервисы профиля `legacy-import` до запуска приложения.

Перед первым запуском: [локальное окружение](https://github.com/jpegMushrum/hikari-secretary-miniapp/blob/main/README.md) или
[production, сертификат и перенос SQLite → PostgreSQL](docs/production.md).
Для production заполните корневой `.env`, `backend/.env` и `targets.json`.
Для локального стека подготовьте корневой `.env` по `.env.example` и
`targets.json` по `targets.example.json`. Для запуска с ботом укажите
`TELEGRAM_BOT_TOKEN` и `ADMIN_IDS` тестового бота в корневом `.env`,
а его цели публикаций — в корневом `targets.json`. При инициализации
тома PostgreSQL создаёт базу `hikari_dev`, а сервис `migrate` применяет
миграции. После этого можно создавать данные через бота или miniapp.
Для локальной генерации ИИ-материалов укажите в корневом `.env`
`DEEPSEEK_API_KEY` и `AI_TOPIC_TARGET_KEY` с ключом тестовой цели из
`targets.json`. Для ежедневной публикации задайте `AI_TOPIC_AUTO_PUBLISH_TIME`
в формате `HH:MM` в часовом поясе `TIMEZONE`. После настройки расписания
администратор может управлять автогенерацией на странице ИИ в miniapp.
[Руководство по ИИ-материалам](https://github.com/jpegMushrum/hikari-secretary-bot/blob/main/docs/ai-materials.md).

## Документация

- [Участникам клуба](https://github.com/jpegMushrum/hikari-secretary-bot/blob/main/docs/participant-guide.md)
- [Администраторам](https://github.com/jpegMushrum/hikari-secretary-bot/blob/main/docs/admin-guide.md)
- [Черновики и miniapp](https://github.com/jpegMushrum/hikari-secretary-bot/blob/main/docs/miniapp-handoff.md)
- [Архитектура платформы](docs/architecture.md)
- [API backend](https://github.com/jpegMushrum/hikari-secretary-backend/blob/main/openapi/openapi.yaml)
- [Roadmap и приоритеты](docs/miniapp-plan.md)
- [Все руководства](docs/README.md)
