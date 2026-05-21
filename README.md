# Trophy Case

A fresh FastAPI/Postgres take on the Worts trophy archive. The old Rails app is useful domain evidence, but this app starts with a clean local development story and explicit domain code for seasons, scoring, and results.

BJCP beer styles are loaded from the 2021 JSON file by Andrew Scholer linked on the BJCP Style Guidelines page.

## Local Docker

Start the app and database:

```sh
./bin/docker-dev
```

The web app will be available at http://localhost:8001 by default.

Public pages are available without logging in. Create, edit, archive, and member-management screens require an admin session. In local Docker mode, visit `/login` and enter an admin member email. If no admin exists yet, set `ADMIN_SETUP_CODE` in `.env` and enter that code once to create the first admin. Set `ADMIN_LOGIN_CODE` in `.env` to require a shared admin code for later admin logins too.

Members in good standing can log in at `/member-login` with an email from the
roster, then land on `/me` for their member profile. The member importer accepts
a CSV upload or a Google Sheets URL from `docs.google.com` and reads the roster
columns `member`, `name`, `paypal_email`, and `list_email`; `member` should be
`1` for members in good standing. In local development without SMTP configured,
login links and codes are printed to the web container logs. Authenticated form
posts use CSRF tokens, and member login email requests are rate limited by email
and client IP.

Good-standing members can submit their own results at `/me/results/new`. Admins
review pending submissions at `/admin/submissions`; approval creates the public
result and rejection leaves the member a private reason to correct and resubmit.

Uploaded result photos and recipe files are stored under `/Users/Shared/Docker/trophy-case/uploads` on the host and served locally from `/uploads`.

To use a different host port:

```sh
WEB_PORT=8010 ./bin/docker-dev
```

## Demo Sandbox

For a disposable seeded demo that does not touch the normal local Docker data:

```sh
./bin/docker-demo up
```

The demo runs at http://localhost:8011 by default, using its own Docker compose
project, Postgres data, uploads directory, and host database port. It resets and
seeds demo rows each time `up` runs.

Demo credentials:

- Admin email: `demo-admin@example.test`
- Admin code: `demo-code`
- Good-standing member email: `alex-list@example.test`
- Lapsed member email for negative tests: `lapsed-list@example.test`

Without SMTP configured, member login links and codes appear in:

```sh
./bin/docker-demo logs
```

Stop the demo while keeping its data:

```sh
./bin/docker-demo down
```

Tear it down and remove all demo data:

```sh
./bin/docker-demo clean --yes
```

Load sample data after the app is running:

```sh
docker compose exec web python -m app.cli seed
```

Load or refresh BJCP styles only:

```sh
docker compose exec web python -m app.cli load-styles
```

Run tests:

```sh
./bin/docker-dev -d
docker compose run --rm web pytest
```

Run migrations manually:

```sh
docker compose run --rm web alembic upgrade head
```

Back up local data:

```sh
docker compose exec web python -m app.cli backup --output /uploads/backups/trophy-case-backup.json
```

Restore a backup:

```sh
docker compose exec web python -m app.cli restore /uploads/backups/trophy-case-backup.json
```

Use `docs/user-testing.md` for the first small tester run.

Reset local data:

```sh
docker compose exec web python -m app.cli reset-data --confirm RESET_DATA
docker compose exec web python -m app.cli load-styles
```

## Services

- `web`: FastAPI, Jinja templates, SQLAlchemy, Alembic.
- `db`: Postgres 16, persisted under `/Users/Shared/Docker/trophy-case/postgres` and exposed on host port `5433`.

All Docker bind mounts live under `/Users/Shared/Docker/trophy-case/`. The `bin/docker-dev` helper mirrors this project into `/Users/Shared/Docker/trophy-case/app`, ensures the Postgres and upload directories exist, then runs `docker compose up --build`. Re-run it after code changes to sync the shared mount; Uvicorn runs with reload enabled.

## Current Shape

- Public result archive at `/results`
- Public competition list at `/competitions`
- Public BJCP style browser at `/styles`
- Public result, member, competition, category, and subcategory detail pages
- Public seasonal leaderboard at `/leaderboard`
- Admin dashboard at `/admin`
- Admin backup, restore, and cleanup tools at `/admin/data`
- Admin audit log at `/admin/audit`
- Admin leaderboard scoring and season settings at `/admin/leaderboard`
- Local result entry form at `/results/new`
- Local competition form at `/competitions/new`
- Admin member roster and member form at `/members`
- Admin CSV exports at `/results.csv`, `/members.csv`, and `/competitions.csv`
- Admin member import from CSV or Google Sheets at `/members/import`
- Admin competition and result CSV imports at `/competitions/import` and `/results/import`
- CSV import preview for members, competitions, and results before committing rows
- Likely duplicate skipping for result CSV imports
- Edit forms for competitions, members, and results from their list pages
- Reversible archive/restore flows for competitions and results
- Deactivate/reactivate flow for members
- Local signed-cookie admin login at `/login`
- Roster-backed member magic-link and code login at `/member-login`
- Member profile redirect at `/me`
- Member-submitted results with admin approval or rejection
- Local photo and recipe-file uploads for results
- Searchable result-entry selectors for members, competitions, and BJCP styles
- Configurable leaderboard season start, placement points, BJCP threshold, and competition type weights
- Leaderboard scoring breakdowns on result and leaderboard pages
- Assisted result CSV resolver for missing members, competitions, and fully described styles
- Optional admin login code and secure-cookie setting for harder local auth
- Healthcheck and production-readiness notes in `docs/production.md`
