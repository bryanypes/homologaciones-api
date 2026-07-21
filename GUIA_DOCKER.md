# Correr HomologaIA con Docker

Imagen publicada y probada:

```
https://hub.docker.com/r/bryanyepes/homologaciones-api
```

> No compartas `.env.docker`/`.env` reales (tienen claves de OpenAI y Brevo). Solo `.env.example`.

---

## Opción 1: sin clonar el repo

Crea una carpeta con estos dos archivos:

**`docker-compose.yml`**
```yaml
services:
  api:
    image: bryanyepes/homologaciones-api:latest
    ports:
      - "8000:8000"
    env_file:
      - .env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started
    volumes:
      - ./uploads:/app/uploads
    restart: unless-stopped

  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: dev
      POSTGRES_PASSWORD: dev
      POSTGRES_DB: homologaciones
    ports:
      - "5433:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U dev -d homologaciones"]
      interval: 5s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    ports:
      - "6380:6379"
    restart: unless-stopped

volumes:
  postgres_data:
```

**`.env`** (basado en [.env.example](.env.example), con tus propias claves):
```
DATABASE_URL=postgresql://dev:dev@postgres:5432/homologaciones
DATABASE_URL_ASYNC=postgresql+asyncpg://dev:dev@postgres:5432/homologaciones
REDIS_URL=redis://redis:6379
SECRET_KEY=cualquier_string_largo
OPENAI_API_KEY=sk-...
```

Nota: `postgres` y `redis` son los hostnames dentro de Docker, no `localhost`.

```bash
docker pull bryanyepes/homologaciones-api:latest
docker compose up -d
```

Listo en `http://localhost:8000/docs`.

---

## Opción 2: clonando el repo

```bash
git clone https://github.com/bryanypes/homologaciones-api
cd homologaciones-api

cp .env.example .env.docker
# editar .env.docker con tus claves

docker compose up -d --build
```

Construye la imagen local y corre las migraciones solo.

---

## Republicar la imagen

```bash
docker compose build api
docker tag homologaciones-api-api:latest bryanyepes/homologaciones-api:latest
docker push bryanyepes/homologaciones-api:latest
```

---

## Seguridad

- `.env.docker`/`.env` no están en git y `.dockerignore` los excluye del build — la imagen publicada no tiene ningún `.env*` adentro (verificado).
- Si alguna vez subiste una imagen antes de ese fix, rota las keys de OpenAI y Brevo.
