# 光 · Hikari Secretary

![Статус: работает](https://img.shields.io/badge/status-running-2EA44F)
[![Bot: последний описанный релиз 0.9.0](https://img.shields.io/badge/bot-0.9.0-5865F2)](bot/CHANGELOG.md)
[![Backend: 0.3.0](https://img.shields.io/badge/backend-0.3.0-00ADD8)](backend/README.md)
[![Miniapp: 0.1.0](https://img.shields.io/badge/miniapp-0.1.0-61DAFB)](miniapp/README.md)

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

Бот работает на Go backend с PostgreSQL. Административная miniapp развёрнута
для закрытого тестирования. Ближайшие задачи — проверка полных сценариев,
исправление ошибок и упрощение интерфейса.

Этот репозиторий — основная точка входа и сборки всей платформы.
Компоненты подключены как Git-сабмодули; состав сборки фиксируется их
коммитами в корневом репозитории.

| Компонент | Версия, указанная в проекте | Назначение |
| --- | --- | --- |
| [Бот](bot/README.md) | `0.9.0` — последний описанный релиз в [истории](bot/CHANGELOG.md) | Telegram-интерфейс и доставка сообщений |
| [Backend](backend/README.md) | `0.3.0` | Бизнес-логика, API, авторизация и PostgreSQL |
| [Miniapp](miniapp/README.md) | `0.1.0` | Административная панель на React и TypeScript |

Эти номера относятся к компонентам. Отдельная версия общего релиза платформы
пока не назначена; последние изменения могут быть новее описанного релиза.

## Запуск

Из корня проекта, после настройки выбранного окружения:

```sh
# Локальная проверка с тестовым ботом
docker compose -f docker-compose.bot-local.yml up -d --build

# Production
docker compose -f docker-compose.production.yml up -d --build
```

Это два самостоятельных стека. Локальный открывает miniapp на
`localhost:5173`; production использует HTTPS с настраиваемыми портами.

Перед первым запуском: [локальное окружение](miniapp/README.md) или
[production, сертификат и перенос SQLite → PostgreSQL](docs/production.md).
Настройки находятся в корневом `.env` и `backend/.env`, цели публикаций —
в `targets.json`. Секреты, сертификаты и рабочие данные не публикуются в Git.

## Документация

- [Участникам клуба](bot/docs/participant-guide.md)
- [Администраторам](bot/docs/admin-guide.md)
- [Черновики и miniapp](bot/docs/miniapp-handoff.md)
- [Архитектура платформы](docs/architecture.md)
- [API backend](backend/openapi/openapi.yaml)
- [Roadmap и приоритеты](docs/miniapp-plan.md)
- [Все руководства](docs/README.md)
