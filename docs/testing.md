# Проверки

Полный набор тестов запускается в контейнере, без доступа к рабочей базе и
реальным Telegram API:

```bash
docker compose run --rm --no-deps -v "${PWD}:/app" bot \
  python -m unittest discover -s tests -v
```

Тесты покрывают миграции SQLite, публикации и очередь доставки, регистрации,
посещаемость, отзывы, административные таблицы, AI-очередь и обработку ошибок
DeepSeek.

Перед изменением или выпуском также проверьте конфигурацию Compose:

```bash
docker compose config --quiet
docker compose build migrate bot
```

После развёртывания просмотрите состояние контейнеров и последние логи:

```bash
docker compose ps
docker compose logs --tail=100 bot
```
