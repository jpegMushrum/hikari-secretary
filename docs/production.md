# Подготовка production и переход с SQLite

Рабочий стек использует PostgreSQL. Обычное обновление запускается вручную
в GitHub Actions. Инструкция по переносу ниже нужна только при первом
переходе со старого SQLite-бота.

## Облачные резервные копии и журналы

На VPS можно включить еженедельное копирование PostgreSQL и медиа
и выгрузку журналов контейнеров в начале каждого часа по UTC в закрытый
S3-совместимый бакет. Журналы хранятся 30 дней. После каждой успешной загрузки
ротация оставляет последнюю копию за каждую ISO-неделю с копиями в скользящем
окне 365 суток. Установку и обновление таймеров, проверку выгрузки и
восстановление на отдельном стенде описывает [руководство по архивированию в S3](s3-archive.md).

## Вложения анонсов

Создайте файл `/etc/hikari-announcements/settings` на основе
[`deploy/announcement-media.env.example`](../deploy/announcement-media.env.example)
и ограничьте его права до `0600`. Для другого пути задайте
`ANNOUNCEMENT_MEDIA_ENV_FILE` в корневом `.env`. Compose передаёт
настройки сервису `backend`.

Укажите `ANNOUNCEMENT_S3_ENDPOINT`, `ANNOUNCEMENT_S3_REGION`,
`ANNOUNCEMENT_S3_BUCKET`, `ANNOUNCEMENT_S3_PREFIX`,
`ANNOUNCEMENT_S3_ACCESS_KEY_ID` и `ANNOUNCEMENT_S3_SECRET_ACCESS_KEY`.
Для Yandex Object Storage пример содержит endpoint
`https://storage.yandexcloud.net`, регион `ru-central1` и префикс
`hikari-production/media/announcements`. Сохраните приватный доступ к
бакету. Дайте сервисному аккаунту чтение и запись объектов только в
префиксе вложений. Для пробного восстановления нужен доступ на чтение.

После применения миграций backend проверьте авторизованную загрузку и
просмотр фотографии, затем перенесите исторические вложения и проверьте
их восстановление на отдельной базе.
[Команды переноса и проверки](s3-archive.md#приватные-вложения-анонсов).

## Подготовка GitHub Actions и VPS

Workflow **Platform checks** запускается вручную в GitHub Actions или
в составе **Deploy production**. Он проверяет версии `bot`, `backend` и `miniapp`,
зафиксированные в проверяемом коммите. Доступ к репозиториям сабмодулей
на GitHub должен быть публичным. Перед изменением ссылок в корне
опубликуйте коммиты в репозиториях компонентов.

На VPS нужен существующий рабочий checkout корневого репозитория на `main`
без локальных правок отслеживаемых файлов, включая сабмодули. Пользователю
развёртывания нужны права записи в каталог и корневой `.env`, доступ к
`origin` и сабмодулям, а также рабочие Git,
Bash, Python 3, `flock`, Docker Engine и Docker Compose v2. Сохраните рабочие
`.env`, `backend/.env`, `targets.json`, сертификат, данные и имя
Compose-проекта. Образы выпускаются для Linux amd64.

### SSH-ключ и доступ к VPS

На компьютере администратора откройте Git Bash. В примерах замените
`deploy`, `vps.example.org`, `22` и путь checkout значениями вашего стенда.
Создайте отдельный ключ для GitHub Actions с пустой парольной фразой
и установите его публичную часть через существующий рабочий SSH-доступ.

```sh
ssh-keygen -t ed25519 -C "hikari-github-actions" -f ~/.ssh/hikari-production -N ''
ssh -p 22 deploy@vps.example.org \
  'umask 077; mkdir -p ~/.ssh; cat >> ~/.ssh/authorized_keys' \
  < ~/.ssh/hikari-production.pub
```

В доверенной консоли VPS, например в панели хостинга, получите строку
`known_hosts` из публичного ключа SSH-сервера. Для порта `22` используйте
в команде имя или IP из `DEPLOY_HOST`. Для другого порта укажите
`[vps.example.org]:2222` с вашим именем и портом.

```sh
sudo awk -v host='vps.example.org' '{print host, $1, $2}' /etc/ssh/ssh_host_ed25519_key.pub
```

Скопируйте строку в локальный файл `~/.ssh/hikari-production-known-hosts`.
Проверьте ключ и доступ к checkout из Git Bash. Команда проверяет ветку,
выводит состояние рабочей копии и проверяет доступ к Docker.

```sh
ssh -p 22 -i ~/.ssh/hikari-production -o IdentitiesOnly=yes -o BatchMode=yes \
  -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$HOME/.ssh/hikari-production-known-hosts" \
  deploy@vps.example.org \
  'cd /srv/hikari-secretary && test "$(git branch --show-current)" = main &&
   git status --short && test -w .env && docker info >/dev/null && docker compose version'
```

На VPS под тем же пользователем проверьте неинтерактивный доступ к GitHub.
Команда `git submodule status --recursive` должна показать все ожидаемые
сабмодули без префиксов `-`, `+` и `U`.

```sh
cd /srv/hikari-secretary
git submodule status --recursive
GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND='ssh -o BatchMode=yes' git ls-remote origin HEAD
GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND='ssh -o BatchMode=yes' \
  git submodule foreach --recursive 'git ls-remote origin HEAD'
```

### Окружение GitHub и доступ к GHCR

В GitHub откройте **Settings → Environments** и создайте окружение
`production`. В **Deployment branches and tags** выберите
**Selected branches and tags** и добавьте правило типа **Branch** со
значением `main`. Храните SSH-секреты только в **Environment secrets**
этого окружения, а переменные задайте в **Environment variables**.
[Настройка окружений в GitHub](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments).

| Тип | Имя | Значение |
| --- | --- | --- |
| Secret | `DEPLOY_SSH_KEY` | Всё содержимое закрытого ключа `~/.ssh/hikari-production`. |
| Secret | `DEPLOY_KNOWN_HOSTS` | Содержимое `~/.ssh/hikari-production-known-hosts`. |
| Variable | `DEPLOY_HOST` | DNS-имя или IP VPS. |
| Variable | `DEPLOY_USER` | Пользователь SSH с доступом к checkout и Docker. |
| Variable | `DEPLOY_PATH` | Абсолютный путь к корневому репозиторию на VPS. |
| Variable | `DEPLOY_PORT` | SSH-порт, по умолчанию `22`. |

Для приватных пакетов GHCR войдите на VPS как пользователь развёртывания.
При запросе пароля введите GitHub personal access token (classic)
с разрешением `read:packages` от аккаунта с доступом на чтение всех трёх
пакетов. Docker должен использовать эти учётные данные при развёртывании.
Для публичных пакетов этот шаг можно пропустить.
[Доступ к Container registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).

```sh
docker login ghcr.io --username YOUR_GITHUB_USER
```

### Проверочный запуск

После публикации файлов workflow в `main` запустите **Actions →
Platform checks → Run workflow** для ветки `main`. Чтобы проверить
также сборку и публикацию образов, запустите **Deploy production** для
`main` с включённым параметром `publish_only`. Этот режим публикует
образы и пропускает подключение к VPS. Возьмите ссылки на образы по digest
из сводки запуска. Для проверки доступа к GHCR скачайте подготовленные
образы на VPS от имени пользователя развёртывания. Подставьте полные
ссылки из сводки вместо примеров ниже.

```sh
docker pull 'ghcr.io/OWNER/hikari-secretary-backend@sha256:BACKEND_DIGEST'
docker pull 'ghcr.io/OWNER/hikari-secretary-bot@sha256:BOT_DIGEST'
docker pull 'ghcr.io/OWNER/hikari-secretary-miniapp@sha256:MINIAPP_DIGEST'
```

## Обновление действующего стенда

Этот порядок подходит для production, уже работающего с PostgreSQL.

В GitHub Actions выберите **Deploy production → Run workflow**, укажите
ветку `main`, оставьте `publish_only` выключенным и запустите workflow.
Он выполняет интеграционные проверки,
собирает образы и публикует их в GHCR как
`ghcr.io/<owner>/hikari-secretary-backend`,
`ghcr.io/<owner>/hikari-secretary-bot` и
`ghcr.io/<owner>/hikari-secretary-miniapp` с тегами по SHA коммита.
На VPS workflow по SSH передаёт commit платформы и ссылки на образы по
digest. Compose загружает готовые образы и ждёт готовности PostgreSQL и
успешного применения миграций перед запуском backend. Затем проверяется
готовность backend и miniapp, а также состояние контейнера бота. Серверный скрипт
сохраняет ссылки в `BACKEND_IMAGE`, `BOT_IMAGE` и `MINIAPP_IMAGE`
в корневом `.env`. При сбое смотрите вывод workflow и состояние контейнеров
на VPS через `docker compose -f docker-compose.production.yml ps -a`
и `docker compose -f docker-compose.production.yml logs --tail=100`.
Восстановление после сбоя выполняется вручную с учётом уже применённых
миграций.

Снимок и импорт запускаются отдельно в профиле `legacy-import`. После
развёртывания откройте «Отзывы» в Telegram под администратором, найдите
отзыв по известному ID и проверьте, что фильтр из карточки участника
показывает отзывы именно этого человека.

## Управление сезонами клуба

После развёртывания версии с поддержкой нужного сезона выберите в GitHub
**Actions → Manage club season → Run workflow** для ветки `main`.
Подтвердите запуск, если этого требуют настройки окружения `production`.
Workflow выполняет выбранную команду в работающем контейнере backend.
Сборка и обновление контейнеров для управления сезоном не требуются.

- Для подготовки выберите `start-santa`. Команда `/app/api santa-start`
  создаёт сезон в состоянии подготовки или возвращает текущий незавершённый
  сезон с его настройками. После успешного запуска откройте «Тайный Санта»
  в административном меню miniapp, укажите бюджет, срок записи, время обмена
  и интервал напоминания. Даты в форме вводятся по Москве и передаются в API
  в UTC. Пункт в меню участников появится после «Открыть участникам».
- Для завершения возьмите число из заголовка «Сезон №…» в панели
  администратора, выберите `close-santa` и передайте это число в `season_id`.
  Команда `/app/api santa-close SEASON_ID` архивирует указанный сезон.
  Повторный запуск с тем же ID безопасен для следующего сезона. Проверьте
  результат workflow и обновите miniapp. Пункт исчезнет из обоих меню.
- Для выборов маскота выберите `start-mascot`. Команда `/app/api mascot-start`
  создаёт сезон в подготовке или возвращает текущий незавершённый сезон.
  Откройте «Выборы маскота» в административном меню, задайте дату и нажмите
  «Открыть приём заявок». Пункт появится и у участников.
- Для архивации выборов выберите `close-mascot` и передайте номер из панели
  администратора в `season_id`. Команда `/app/api mascot-close SEASON_ID`
  архивирует указанный сезон выборов. После успешного workflow и обновления
  miniapp пункт исчезнет из меню.

Для ранее приостановленного сезона в панели miniapp доступна кнопка
«Возобновить доступ». Она открывает тот же сезон с сохранёнными заявками
и назначениями.

При утверждении жеребьёвки итоговые назначения и задания на доставку
сохраняются вместе. Для доставки личных сообщений и напоминаний нужен
работающий Telegram-бот с включёнными фоновыми заданиями. При настроенном
`MINIAPP_URL` сообщения содержат кнопку перехода к карточке сезона.

### Изображения для выборов маскота

Для приёма концептов разместите на сервере файл настроек по примеру
[`deploy/mascot-media.env.example`](../deploy/mascot-media.env.example).
Production Compose по умолчанию ищет его по пути `/etc/hikari-mascot/settings`.
Путь можно переопределить через `MASCOT_MEDIA_ENV_FILE` в корневом `.env`.
Используйте приватный бакет и отдельный ключ с разрешениями `GetObject`,
`PutObject` и `DeleteObject` в пределах префикса выборов. Ограничьте права
на файл. Compose передаёт эти настройки только backend. Файл опционален
для запуска стека, для загрузки работ требуется настроенное хранилище.

## Сеть и HTTPS

- Внешний HTTPS-порт задаёт `MINIAPP_HTTPS_PORT` (по умолчанию `8443`),
  HTTP-порт — `MINIAPP_HTTP_PORT` (по умолчанию `880`). Оба должны быть
  свободны на выбранном адресе сервера. В контейнере nginx слушает 443 и 80.
- HTTP перенаправляет на настроенный домен и HTTPS-порт с сохранением пути
  и строки запроса. Путь `/healthz` отдаёт статус напрямую. Бот использует
  тот же HTTPS-порт в кнопке miniapp.
- PostgreSQL, backend и внутренний Bot API не публикуются на хосте.
- Nginx отдаёт собранный frontend и проксирует `/api/v1/admin/` и
  `/api/v1/member/`.
  `/internal/`, остальные `/api/` и dev gateway недоступны.
- Backend проверяет настоящую подпись Telegram initData и список админов.
  Открытие URL в обычном браузере не даёт административного доступа.
- Бот использует polling; входящий webhook для него на этих портах не нужен.

Каталог `MINIAPP_TLS_DIR` содержит `fullchain.pem` и
`privkey.pem`. Он подключается read-only. Если Certbot создаёт симлинки,
нужно предоставить nginx доступ к их целевым файлам либо устанавливать
реальные файлы в этот каталог. Приватный ключ, `.env` и данные не коммитятся.
По умолчанию `./data-tls` уже исключён из Git правилом `data*/`.
Без сертификата nginx намеренно не запустится; HTTP-only fallback нет.
После обновления файлов сертификата проверьте конфигурацию и перечитайте её:

```sh
docker compose -f docker-compose.production.yml exec miniapp nginx -t
docker compose -f docker-compose.production.yml exec miniapp nginx -s reload
```

Привязка DNS A/AAAA к серверу, доступность выбранных портов в firewall и публично
доверенный сертификат проверяются перед запуском в Telegram. Выпуск и
продление сертификата выполняются отдельно от Compose. DNS-01 не требует свободного 80/443.

## Конфигурация

При первой настройке подготовьте три файла. Корневой `.env` заполняется
по `.env.example`, `backend/.env` — по `backend/.env.example`, цели
Telegram в `targets.json` — по `targets.example.json`. При обновлении
сохраняйте рабочие файлы. Production Compose по умолчанию читает настройки
бота из корневого `.env`.

Пример сетевых настроек и путей с портами по умолчанию:

```dotenv
MINIAPP_DOMAIN=hikari.jpegmushrum.ru
MINIAPP_HTTP_PORT=880
MINIAPP_HTTPS_PORT=8443
MINIAPP_BIND_ADDRESS=0.0.0.0
MINIAPP_TLS_DIR=./data-tls
LEGACY_DATA_DIR=./data
BOT_DATA_DIR=./data
```

`LEGACY_DATA_DIR` — каталог исходной `bot.sqlite3`, `BOT_DATA_DIR` — рабочий
каталог медиа нового стека. Их можно оставить одинаковыми: SQLite читается
только для снимка, новый бот работает через Go API и не пишет в SQLite.
Сохраните пути и файлы медиа старого бота: импорт не копирует изображения.

В `backend/.env` задайте PostgreSQL пароль и соответствующий `DATABASE_URL`
с хостом `database:5432`, настоящий токен того же Telegram-бота,
`ADMIN_TELEGRAM_IDS` и `BOT_SERVICE_TOKEN`. В корневом `.env` должны быть
тот же токен бота, тот же service token и соответствующий `ADMIN_IDS`.
Нельзя переносить фиктивные токены и dev admin ID из локального стенда.
Production Compose сам задаёт `MINIAPP_URL` с доменом и портом.

## Кнопка «Панель клуба»

Бот назначает общую кнопку «Панель клуба», которая открывает `/events`.
Пользователям из `ADMIN_IDS` он назначает личную кнопку для `/admin/events`.
Команда `/start` в личном чате обновляет кнопку администратора, а у
остальных сбрасывает прежнее личное меню к общему.
Кнопка «Открыть черновик в miniapp» открывает конкретную публикацию.

При старте бот обновляет меню текущих и ранее известных администраторов.
Список хранится рядом с media в `miniapp-menu-admins.json`. После удаления
администратора из `ADMIN_IDS` его кнопка открывает режим участника.
Удалите его и из `ADMIN_TELEGRAM_IDS` backend, который проверяет роль при
каждом запросе к Admin API.

Nginx проксирует `/api/v1/admin/` и `/api/v1/member/` в backend.
`REMINDER_OPTIONS_MINUTES` в корневом `.env` задаёт варианты напоминания
для обоих интерфейсов. При отдельном `BOT_ENV_FILE` задайте боту те же
значения. По умолчанию используется `30,60,120,360,1440`.

`FIRST_VISIT_ADMIN_USERNAME` в корневом `.env` задаёт необязательный контакт
для участников, которые указали в профиле, что не учатся в ИТМО. Укажите
имя пользователя Telegram с `@` или без него, например `@club_admin`.
Compose передаёт значение в backend. При первой успешной регистрации через
miniapp контакт появляется в окне подтверждения, а backend сохраняет
задание `registration.first_visit` в очереди. Для отправки сообщения
после закрытия miniapp фоновые задачи бота должны быть включены
(`BOT_BACKGROUND_WORKERS_ENABLED=true`). При записи в чате бот отправляет
контакт сразу после подтверждения. При проверке истории учитываются
и отменённые записи. Если значение пустое, контакт скрыт.

## Переход с серверной ветки main и SQLite

Фактический переход требует короткой остановки старого бота.
Не запускайте два polling-процесса с одним токеном. Нельзя импортировать
локальную демонстрационную БД вместо серверной.

1. Зафиксировать текущий commit main и версии сабмодулей. Сохранить отдельно
   рабочие `.env`, `targets.json`, весь каталог данных и медиа. Проверить
   реальные пути и имя файла SQLite: команда ниже ожидает `bot.sqlite3`.
2. Остановить старого бота средствами его текущего Compose. После остановки
   сделать резервную копию всего каталога данных, включая `-wal` и `-shm`,
   если они есть. Не копировать один файл SQLite во время записи.
3. Обновить код и сабмодули, сохранить серверные конфиги. Проверить, что
   целевой volume PostgreSQL предназначен для этого перехода и не содержит
   тестовой БД или ранее установленного маркера импорта. Volume не удалять.
4. После подключения сертификата проверить конфигурацию. Для первого
   переноса можно собрать приложения из checkout выбранного релиза,
   оставив `BACKEND_IMAGE`, `BOT_IMAGE` и `MINIAPP_IMAGE` незаданными.
   На VPS с ограниченной памятью запустите **Deploy production** на
   `main` с флагом `publish_only`. После тестов и сборки GitHub покажет
   три ссылки по digest в сводке запуска. Укажите их в корневом `.env`
   на VPS с тем же коммитом и замените команду
   `build backend bot miniapp` на `pull backend bot miniapp`.
   Отдельно соберите импортёр:

```sh
docker compose -f docker-compose.production.yml config --quiet
docker compose -f docker-compose.production.yml build backend bot miniapp
docker compose -f docker-compose.production.yml --profile legacy-import build backend-import
```

5. Выполнить снимок, миграции и импорт без запуска бота:

```sh
docker compose -f docker-compose.production.yml run --rm legacy-snapshot
docker compose -f docker-compose.production.yml up -d --wait database
docker compose -f docker-compose.production.yml run --rm --no-deps backend-migrate
docker compose -f docker-compose.production.yml run --rm --no-deps backend-import
```

Сервисы `legacy-snapshot` и `backend-import` входят в профиль `legacy-import`.
При явном запуске сервиса через `run` Compose активирует его профиль.
Импортёр собирается из `backend/Dockerfile.import-legacy` в отдельный образ
`hikari-secretary-import-legacy:local`. По умолчанию он читает
`/legacy/bot.sqlite3` и выдаёт отчёт JSON в режиме dry-run.
`--no-deps` в командах переноса используется после выполнения предыдущих
шагов: для импорта должны быть готовы PostgreSQL, миграции и снимок.

Проверьте в отчёте dry-run `"valid": true`, количества профилей,
мероприятий, регистраций и отзывов, а также прогноз посещений.
Публикации и задания ИИ сверяются после импорта. Для записи выполните:

```sh
docker compose -f docker-compose.production.yml run --rm --no-deps backend-import --sqlite /legacy/bot.sqlite3 --apply --json
```

При ошибке любого шага остановите перенос. После остановки старого бота
SQLite и журналы `-wal`/`-journal` копируются
из read-only каталога во временный записываемый каталог. Там SQLite
восстанавливает служебный SHM и создаёт снимок через backup API
(включая зафиксированные WAL-записи). Снимок проверяется и атомарно сохраняется
в отдельном volume `legacy_snapshot`. Существующий снимок никогда не
перезаписывается, даже если исходный SQLite изменился. Повреждённый снимок
останавливает запуск. PostgreSQL-импорт транзакционный и имеет маркер
`legacy_sqlite_import_complete`: повторный запуск не затирает новые данные.

Переносятся профили/идентичности, мероприятия, регистрации, посещения,
отзывы, ожидающие публикации и поддерживаемое состояние ИИ. Старые черновики
и завершённые публикации **не входят в текущий импорт**; их оригиналы
остаются в полном снимке SQLite. Это перенос доменных данных, не точная
копия всех таблиц. До перехода закончите важные старые черновики либо
сохраните сообщения для повторной пересылки новому боту.

6. Проверить импорт и очереди. Для предварительного просмотра без фоновых
   рассылок временно задать `BOT_BACKGROUND_WORKERS_ENABLED=false` в `.env`.
   Затем запустить стек:

```sh
docker compose -f docker-compose.production.yml up -d --no-build backend bot miniapp
docker compose -f docker-compose.production.yml ps
docker compose -f docker-compose.production.yml logs --tail=100 backend-migrate backend bot miniapp
```

При первом переносе запускайте обычный стек после проверки успешного импорта.
Обычный запуск выполняет цепочку PostgreSQL → миграции → backend → bot/miniapp.
Если HTTPS-конфигурация ошибочна, бот может работать независимо
от miniapp; проверьте обе службы. После проверки очередей вернуть workers
в true и пересоздать bot. Просроченные задания могут отправиться сразу.

С этого момента единственный источник новых данных — PostgreSQL.
SQLite не синхронизируется обратно. На последующих обновлениях запускайте
тот же Compose с тем же именем проекта и сохранёнными volumes.
**Не выполнять `down -v`**: это удалит PostgreSQL и снимок.

Откат до появления новых записей: остановить новый бот и вернуть старую
версию с сохранённой SQLite. После приёма новых регистраций/отзывов простой
возврат на SQLite потеряет эти изменения: сначала сохранить PostgreSQL
и отдельно согласовать перенос новых данных. Автоматического обратного
импорта нет.

## Проверки перед закрытым тестом

- После `/start` участник открывает «Панель клуба», видит свои мероприятия,
  профиль и отзывы. Его Telegram initData получает `403` на Admin API.
- Администратор открывает административные мероприятия и переключается в
  режим участника и обратно из меню miniapp.
- Новый rich message → черновик → публикация сразу/по времени → регистрация
  и отмена → посещение → отзыв; статистика соответствует действиям.
- Медиа доступны с авторизацией, внутренний API недоступен извне.
- Перезапуск не повторяет импорт/доставленные задания и сохраняет новые данные.
- Telegram на телефоне и desktop корректно открывает URL с настроенным HTTPS-портом.

Проверки подготовки без запуска production:

```sh
python -m unittest discover -s deploy
```

Они проверяют снимок SQLite и итоговый Compose; bot unit-тесты проверяют
админские кнопки. TLS и открытие miniapp в Telegram проверяйте на публичном домене с действующим сертификатом.

## Диагностика первого переноса

Если старый скрипт снимка упал на `old.backup(new)` с
`unable to open database file`, обновите `deploy/snapshot_sqlite.py` и
повторите `docker compose -f docker-compose.production.yml run --rm legacy-snapshot`.
Образ пересобирать не нужно: скрипт подключён bind mount. Старый бот должен
оставаться остановленным. Не удаляйте исходные WAL/SHM и не включайте
`immutable=1` при чтении источника: зафиксированные изменения могут быть
только в WAL. Volume снимка и исходную базу удалять не нужно.


Мигратор читает только `DATABASE_URL`. Если старый образ завершился с
`invalid configuration: read targets`, проверьте `BACKEND_IMAGE` и загрузите
подготовленную версию через `docker compose -f docker-compose.production.yml
pull backend-migrate`, затем повторите `run --rm backend-migrate`.
Успешный dry-run SQLite не означает, что миграции
PostgreSQL применены: импорт с записью выполняется только после успешного
завершения мигратора.
