# Production Guide

This guide is for running Trophy Case on a DigitalOcean Droplet at
`https://trophycase.worts.club`. The production stack is containerized with
`compose.prod.yaml`: Postgres, the FastAPI web app, and Caddy for HTTPS.

## Droplet

Create an Ubuntu LTS Droplet with SSH keys, monitoring, and backups enabled.
Point the DNS `A` record for `trophycase.worts.club` at the Droplet IP before
starting Caddy so certificate issuance can succeed.

Install Docker Engine and the Compose plugin using Docker's Ubuntu repository:

```sh
sudo apt-get update
sudo apt-get install -y ca-certificates curl git openssl sudo ufw
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" | sudo tee /etc/apt/sources.list.d/docker.list
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Use a deploy user and expose only SSH, HTTP, and HTTPS:

```sh
sudo adduser deploy
sudo usermod -aG sudo,docker deploy
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
```

Log in again as `deploy` for the remaining steps.

## Files

The production compose file bind-mounts persistent data from `/opt/trophy-case`.
Create the directories before the first deploy:

```sh
sudo mkdir -p /opt/trophy-case/app /opt/trophy-case/postgres /opt/trophy-case/uploads /opt/trophy-case/caddy/data /opt/trophy-case/caddy/config /opt/trophy-case/backups
sudo chown -R deploy:deploy /opt/trophy-case
sudo chown -R 10001:10001 /opt/trophy-case/uploads
chmod 700 /opt/trophy-case/backups
```

Copy or clone the project into `/opt/trophy-case/app`. Keep `.env` only on the
Droplet.

## Environment

Start from `.env.prod.example` and create `/opt/trophy-case/app/.env`.

Required values:

```sh
APP_SECRET_KEY=<openssl rand -hex 32>
POSTGRES_PASSWORD=<openssl rand -hex 32>
ADMIN_LOGIN_CODE=<private shared admin code>
ADMIN_SETUP_CODE=<one-time first-admin setup code>
ACME_EMAIL=<certificate notice email>
PUBLIC_BASE_URL=https://trophycase.worts.club
SESSION_COOKIE_SECURE=true
LOCAL_LOGIN_ENABLED=true
```

For member login emails, configure SMTP. DigitalOcean blocks common outbound
SMTP ports on Droplets, so use your provider's alternate submission port such as
`2525`.

```sh
EMAIL_FROM=trophycase@worts.club
SMTP_HOST=<smtp host>
SMTP_PORT=2525
SMTP_USERNAME=<smtp username>
SMTP_PASSWORD=<smtp password>
SMTP_USE_TLS=true
```

Then lock the file down:

```sh
chmod 600 /opt/trophy-case/app/.env
```

Remove `ADMIN_SETUP_CODE` after the first admin account exists.

## Deploy

From `/opt/trophy-case/app`:

```sh
docker compose -f compose.prod.yaml config --quiet
docker compose -f compose.prod.yaml up -d --build
docker compose -f compose.prod.yaml exec -T web python -m app.cli load-styles
curl -fsS https://trophycase.worts.club/healthz
```

The web service runs `alembic upgrade head` before Uvicorn starts. Caddy serves
ports `80` and `443`, stores certificates in `/opt/trophy-case/caddy/data`, and
reverse proxies to the internal web container. Postgres stays on the internal
network; the web container also joins an outbound network so SMTP and Google
Sheet imports can reach the internet.

For later deploys:

```sh
cd /opt/trophy-case/app
docker compose -f compose.prod.yaml up -d --build
docker compose -f compose.prod.yaml exec -T web python -m app.cli load-styles
curl -fsS https://trophycase.worts.club/healthz
```

## First Admin

Open `https://trophycase.worts.club/login`, enter the first admin email or one
of that admin member's roster aliases, and use `ADMIN_SETUP_CODE`. After
`/admin` works, remove `ADMIN_SETUP_CODE` from `.env` and restart web:

```sh
docker compose -f compose.prod.yaml up -d web
```

Keep at least two active admins once the roster is imported.

## Member Login

Members log in at `/member-login`. If the email belongs to an active member in
good standing, the app sends one email containing both:

- a one-time magic login link
- a six-digit fallback login code

Set `PUBLIC_BASE_URL=https://trophycase.worts.club` so magic links use the public
HTTPS hostname. Production compose requires `EMAIL_FROM`, `SMTP_HOST`,
`SMTP_USERNAME`, and `SMTP_PASSWORD`; once those are configured, the admin
dashboard reports member login delivery as `SMTP`. Without SMTP in local
development, links and codes are printed to web logs.

Before inviting members, test a good-standing member and a lapsed/inactive member.

## Member Submissions

Good-standing members can submit their own winnings at `/me/results/new`. New
submissions stay out of the public archive until an admin approves them at
`/admin/submissions`; approval creates the public result and copies any uploaded
recipe or photo into the result upload directory. Admins can approve individual
rows from the queue or approve all currently pending submissions at once.
Rejections stay visible to the member with the admin's reason. Admins can edit a
member and clear `Require result submission review`; that member's future
submissions publish immediately while still keeping an approved submission
record.

Logged-in good-standing members can also add competitions at `/competitions/new`.
New competitions are public immediately; edits, imports, archive, and restore
remain admin-only.

## Backups

The app's admin JSON backup is useful, but production backup needs both Postgres
and uploaded files. Use the checked-in backup script from the project root:

```sh
cd /opt/trophy-case/app
bin/prod-backup /opt/trophy-case/backups
```

The script briefly stops the web service while it dumps Postgres and archives
uploads, then starts it again. It creates a timestamped directory containing:

```text
manifest.txt
postgres.dump
uploads.tar.gz
SHA256SUMS
```

Schedule it with cron, then copy backups off the Droplet:

```cron
15 3 * * * cd /opt/trophy-case/app && /opt/trophy-case/app/bin/prod-backup /opt/trophy-case/backups >>/var/log/trophy-case-backup.log 2>&1
```

## Restore

Restores replace the production database and uploads. Take a fresh backup first
unless the Droplet is already unusable.

```sh
cd /opt/trophy-case/app
bin/prod-restore /opt/trophy-case/backups/trophy-case-20260520T150000Z trophycase.worts.club
```

The script verifies backup files, asks you to type `RESTORE trophycase.worts.club`,
stops web, restores Postgres, replaces `/uploads` through a one-off web
container, and starts web again.

After restoring:

```sh
curl -fsS https://trophycase.worts.club/healthz
docker compose -f compose.prod.yaml logs --tail=100 web
```

## Checklist

- DNS for `trophycase.worts.club` points to the Droplet.
- Firewall exposes only SSH, HTTP, and HTTPS.
- `.env` exists on the Droplet, is mode `600`, and is not committed.
- `APP_SECRET_KEY`, `POSTGRES_PASSWORD`, `ADMIN_LOGIN_CODE`, and SMTP password are
  unique production secrets.
- `PUBLIC_BASE_URL=https://trophycase.worts.club`.
- `SESSION_COOKIE_SECURE=true`.
- `/opt/trophy-case/uploads` is writable by container UID `10001`.
- `ADMIN_SETUP_CODE` is removed after first-admin setup.
- `/healthz` returns 200 through HTTPS.
- `/admin` redirects before login and opens after admin login.
- Admin dashboard reports member login delivery as `SMTP`.
- A good-standing member can use both magic link and six-digit code.
- A lapsed or inactive member does not receive a login email.
- A good-standing member can submit a result and an admin can approve or reject it.
- A trusted member can submit a result without entering the admin review queue.
- A logged-in member can add a competition without admin review.
- `bin/prod-backup` produces both `postgres.dump` and `uploads.tar.gz`.
- A recent backup has been restored successfully in a throwaway environment.

## Dependency Updates

Production Docker builds use `requirements-prod.txt` and local dev builds use
`requirements-dev.txt` as pip constraints. When intentionally upgrading Python
dependencies, refresh those lock files in a disposable/local environment, rebuild
the runtime image, and run the full test suite before deploying.
