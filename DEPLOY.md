# Как выложить Капсулку на свой сервер

Подходит любой VPS с Ubuntu 22.04/24.04 и Docker. Хватает 2 vCPU и 2 ГБ RAM: сама программа занимает ~150 МБ,
а память нужна в основном на сборку фронтенда.

## 0. Автодеплой из GitHub (рекомендуется)

Файл `.github/workflows/deploy.yml` при каждом push в `main` собирает образы в GitHub Actions
и по SSH привозит их на сервер в `/opt/cureme`. Сервер не качает образы с Docker Hub и не тратит память на сборку.

Один раз на своём компьютере (WSL):

```bash
ssh-keygen -t ed25519 -f ~/.ssh/cureme_deploy -N "" -C github-actions   # отдельный ключ только для деплоя
ssh-copy-id -i ~/.ssh/cureme_deploy.pub root@158.255.7.113
cat ~/.ssh/cureme_deploy                     # → секрет SSH_PRIVATE_KEY
ssh-keyscan -t ed25519 158.255.7.113         # → секрет SSH_KNOWN_HOSTS
```

Секреты добавляются в GitHub: Settings → Secrets and variables → Actions → New repository secret.
Адрес сервера и домен записаны в `env` в начале workflow: основной домен `kapsulka.ru` (`CUREME_DOMAIN`),
а с `www.kapsulka.ru`, `kapsulka.online` и прежнего адреса `158-255-7-113.sslip.io` (`CUREME_OLD_DOMAIN`) Caddy делает редирект на основной. Запустить деплой вручную можно
на вкладке Actions → Deploy → Run workflow. Ниже описан ручной способ, если автодеплой не нужен.

## 1. Домен

Камера в браузере работает только по HTTPS, а HTTPS-сертификат выдают на домен, не на IP.
Купите домен (например, `.ru` у регистратора) и создайте у него DNS-запись:

```
A   cureme.example.ru   →   <IP сервера>
```

## 2. Сервер

```bash
ssh root@<IP сервера>

# вход по ключу вместо пароля (ключ создаётся на своём компьютере: ssh-keygen -t ed25519)
# и сразу смените root-пароль: passwd

ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw --force enable

git clone https://github.com/Zimin0/CureMe.git && cd CureMe
cat > .env <<ENV
CUREME_DOMAIN=cureme.example.ru
CUREME_SECRET_KEY=$(openssl rand -hex 32)
ENV

docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Полный список мер по защите сервера (SSH без паролей, fail2ban, резервные копии) — в [SECURITY.md](SECURITY.md).

Через минуту откройте `https://cureme.example.ru`: Caddy сам получит сертификат Let's Encrypt.

## 3. Проверить поиск по штрихкоду с сервера

```bash
docker compose exec app python -m app.websearch 4605077018932
```

Должно вывести `Ларингобакт…`. Если поисковики с этого сервера недоступны, будет `None`:
приложение продолжит работать, просто название незнакомого лекарства придётся вписать руками.

## 4. Обновление

```bash
cd CureMe && git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Миграции базы применяются сами при старте контейнера.

## 5. Резервная копия

База живёт в PostgreSQL (том `cureme_pg-data`), фото лекарств в томе `cureme_cureme-data`. Команды выполняются в `/opt/cureme`:

```bash
# база: SQL-дамп, можно снимать на ходу
docker compose exec -T db pg_dump -U cureme cureme | gzip > cureme-db-$(date +%F).sql.gz
# фото
docker run --rm -v cureme_cureme-data:/data -v "$PWD":/backup alpine tar czf /backup/cureme-media-$(date +%F).tar.gz -C /data media
```

Восстановить базу из дампа: `gunzip -c cureme-db-ДАТА.sql.gz | docker compose exec -T db psql -U cureme cureme` (в пустую базу).

## 6. Переезд с SQLite на PostgreSQL

Раньше база была файлом `/data/cureme.db`. Первый деплой с Postgres переносит её сам:

1. Перед перезапуском деплой снимает копию `/data/cureme.db.before-postgres`.
2. Контейнер приложения при старте догоняет старую базу миграциями, создаёт схему в Postgres и одной транзакцией копирует все таблицы. В логе видно `Перенесено: users N, medicines N, …`.
3. Файл переименовывается в `/data/cureme.db.imported-<время>`. Если в Postgres уже есть пользователи, перенос больше не запускается.

Если перенос упадёт, транзакция откатится, SQLite-файл останется на месте, а деплой покажет лог с ошибкой. Откатиться на SQLite можно так: скопировать `/data/cureme.db.before-postgres` обратно в `/data/cureme.db` и задеплоить прежний `docker-compose.yml` из git. Всё, что записали уже в Postgres, при этом в SQLite не попадёт.
