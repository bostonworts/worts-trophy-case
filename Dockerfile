FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

FROM base AS build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY requirements-prod.txt ./
COPY app ./app

RUN pip install --upgrade pip \
    && pip wheel --no-cache-dir --constraint requirements-prod.txt --wheel-dir /wheels .

FROM base AS dev

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY requirements-prod.txt requirements-dev.txt ./
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./

RUN pip install --upgrade pip \
    && pip install --no-cache-dir --constraint requirements-dev.txt -e ".[dev]"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS runtime

ARG APP_UID=10001
ARG APP_GID=10001

COPY --from=build /wheels /wheels

RUN pip install --no-cache-dir --no-index --find-links=/wheels trophy-case \
    && rm -rf /wheels \
    && groupadd --gid "${APP_GID}" app \
    && useradd --uid "${APP_UID}" --gid app --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /uploads \
    && chown app:app /uploads

COPY --chown=app:app migrations ./migrations
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app app ./app

USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
