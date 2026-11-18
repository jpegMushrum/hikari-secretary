# Документация платформы Hikari Secretary

[Главная страница платформы](../README.md) содержит информацию о клубе,
возможностях и версиях. Здесь собраны подробные руководства по устройству,
разработке и эксплуатации.

| Документ | Содержание |
| --- | --- |
| [История релизов](../CHANGELOG.md) | Выпуски backend, miniapp, бота и изменения платформы |
| [Структура репозитория](repository-layout.md) | Роли `bot/`, `backend/`, `miniapp/`, Compose и порядок выделения сабмодулей |
| [Целевая архитектура](architecture.md) | Границы модулей, адаптеров, доступа и перенос с SQLite на PostgreSQL |
| [Каталог use cases](use-cases.md) | Согласованные сценарии платформы, акторы, правила и приоритет переноса |
| [План Mini App и roadmap](miniapp-plan.md) | Стек и стиль, браузерная версия → ранний запуск для администраторов в Telegram → расширение; разделы, таблицы, отложенные задачи и идеи |
| [Запуск браузерной Mini App](https://github.com/jpegMushrum/hikari-secretary-miniapp/blob/main/README.md) | localhost:5173, изолированный dev compose, архитектура frontend, тесты и текущие границы |
| [Production и переход с SQLite](production.md) | Compose, HTTPS на 8443/880, админские кнопки, снимок и импорт, порядок запуска и откат |
| [Модель данных и перенос](domain-model.md) | Целевая модель первого среза и безопасный план SQLite → PostgreSQL |
| [Документация бота](https://github.com/jpegMushrum/hikari-secretary-bot/blob/main/docs/README.md) | Настройка, эксплуатация, сценарии и архитектура текущего Python-бота |

Корневой Compose собирает backend и bot. Рабочий запуск текущего бота описан
в [`bot/docs/getting-started.md`](https://github.com/jpegMushrum/hikari-secretary-bot/blob/main/docs/getting-started.md).
