# Homologaciones API

Backend para el sistema de homologaciones académicas universitarias con procesamiento por IA.

## Stack

- **Framework:** FastAPI + Python 3.12
- **Base de datos:** PostgreSQL 16 + Alembic
- **Caché:** Redis 7
- **Eventos:** Kafka
- **IA:** Claude (Anthropic)
- **Contenedores:** Docker + Docker Compose
- **CI/CD:** GitHub Actions
- **Gestor de dependencias:** uv

## Flujo del sistemaEstudiante sube PDFs → Coordinador activa IA → Claude procesa → Rector aprueba/rechaza

### Estados de una solicitudBORRADOR → ENVIADA → EN_REVISION → PROCESANDO_IA → PENDIENTE_RECTOR → APROBADA / RECHAZADA

### Roles

| Rol | Permisos |
|-----|----------|
| Estudiante | Crear solicitudes, subir PDFs, ver sus solicitudes |
| Coordinador | Revisar solicitudes, activar procesamiento IA |
| Rector | Aprobar o rechazar homologaciones |

## Requisitos

- Docker Desktop
- uv (`pip install uv`)

## Instalación local

```bashClonar el repo
git clone https://github.com/tu-usuario/homologaciones-api
cd homologaciones-apiInstalar dependencias
uv syncConfigurar variables de entorno
cp .env.example .env
Editar .env con tus valoresLevantar base de datos
docker run -d --name postgres -e POSTGRES_USER=dev -e POSTGRES_PASSWORD=dev -e POSTGRES_DB=homologaciones -p 5432:5432 postgres:16Correr migraciones
uv run alembic upgrade headArrancar la API
uv run uvicorn app.main:app --reload

## Instalación con Docker

```bashConfigurar variables de entorno para Docker
cp .env.example .env.docker
Editar .env.docker con tus valoresLevantar todo el stack
docker compose up

## Variables de entorno

| Variable | Descripción | Ejemplo |
|----------|-------------|---------|
| `DATABASE_URL` | URL de PostgreSQL (sync) | `postgresql://dev:dev@localhost:5432/homologaciones` |
| `DATABASE_URL_ASYNC` | URL de PostgreSQL (async) | `postgresql+asyncpg://dev:dev@localhost:5432/homologaciones` |
| `REDIS_URL` | URL de Redis | `redis://localhost:6379` |
| `SECRET_KEY` | Clave para JWT | `mi_clave_secreta` |
| `ANTHROPIC_API_KEY` | API key de Anthropic | `sk-ant-...` |
| `KAFKA_BOOTSTRAP_SERVERS` | Servidor Kafka | `localhost:9092` |

## Endpoints principales

| Método | Ruta | Rol | Descripción |
|--------|------|-----|-------------|
| POST | `/api/v1/auth/register` | Público | Registro de usuario |
| POST | `/api/v1/auth/login` | Público | Login, retorna JWT |
| POST | `/api/v1/solicitudes/` | Estudiante | Crear solicitud |
| PATCH | `/api/v1/solicitudes/{id}/enviar` | Estudiante | Enviar solicitud |
| PATCH | `/api/v1/solicitudes/{id}/revisar` | Coordinador | Tomar en revisión |
| POST | `/api/v1/documentos/{id}/pensum-origen` | Estudiante | Subir PDF origen |
| POST | `/api/v1/documentos/{id}/pensum-destino` | Estudiante | Subir PDF destino |
| POST | `/api/v1/homologaciones/{id}/procesar` | Coordinador | Activar IA |
| PATCH | `/api/v1/solicitudes/{id}/aprobar` | Rector | Aprobar homologación |
| PATCH | `/api/v1/solicitudes/{id}/rechazar` | Rector | Rechazar homologación |

Documentación interactiva disponible en `http://localhost:8000/docs`

## Tests

```bashuv run pytest tests/ -v

## Estructura del proyectohomologaciones-api/
├── app/
│   ├── api/v1/          # Endpoints
│   ├── core/            # Config, DB, seguridad, deps
│   ├── models/          # Modelos SQLAlchemy
│   ├── schemas/         # Schemas Pydantic
│   ├── services/        # IA, PDF, Kafka, Email
│   └── workers/         # Consumidores Kafka
├── tests/
├── alembic/             # Migraciones
├── docker-compose.yml
├── Dockerfile
└── pyproject.toml
Sube el README:bashgit add .
git commit -m "docs: add README"
git push