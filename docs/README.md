# Документация платформы Hikari Secretary

[Главная страница платформы](../README.md) содержит информацию о клубе,
возможностях и версиях. Здесь собраны подробные руководства по устройству,
разработке и эксплуатации.

| Документ | Содержание |
| --- | --- |
| [История релизов](../CHANGELOG.md) | Выпуски backend, miniapp, бота и изменения платформы |
| [Структура репозитория](repository-layout.md) | Роли `bot/`, `backend/`, `miniapp/`, два Compose-стека и обновление сабмодулей |
| [Архитектура](architecture.md) | Границы модулей, адаптеров, доступа и перенос с SQLite на PostgreSQL |
| [Каталог use cases](use-cases.md) | Согласованные сценарии платформы, акторы, правила и приоритет переноса |
| [План Mini App и roadmap](miniapp-plan.md) | Стек и стиль, текущая админская панель, ближайшие задачи, пользовательский режим и идеи |
| [Запуск браузерной Mini App](https://github.com/jpegMushrum/hikari-secretary-miniapp/blob/main/README.md) | localhost:5173, изолированный dev compose, архитектура frontend, тесты и текущие границы |
| [Production и переход с SQLite](production.md) | Compose, настраиваемые порты HTTPS и HTTP, кнопка «Панель клуба», снимок и импорт, порядок запуска и откат |
| [Архивирование production в S3](s3-archive.md) | Настройка таймеров на VPS, резервные копии PostgreSQL и медиа, выгрузка журналов, проверка восстановления |
| [Модель данных и перенос](domain-model.md) | Данные PostgreSQL, файлы медиа и состав ручного импорта из SQLite |
| [Документация бота](https://github.com/jpegMushrum/hikari-secretary-bot/blob/main/docs/README.md) | Настройка, эксплуатация, сценарии и архитектура текущего Python-бота |

Контракты Mini App доступны в [OpenAPI](https://github.com/jpegMushrum/hikari-secretary-backend/blob/main/openapi/openapi.yaml).
Сценарии описаны в руководствах по [Admin API](https://github.com/jpegMushrum/hikari-secretary-backend/blob/main/docs/admin-api.md)
и [Member API](https://github.com/jpegMushrum/hikari-secretary-backend/blob/main/docs/member-api.md).
