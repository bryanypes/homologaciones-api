# HomologaIA — Sistema de Gestión de Homologaciones Académicas (backend)

API de HomologaIA, la plataforma de la Corporación Universitaria Autónoma del Cauca para tramitar solicitudes de homologación. Compara con IA el certificado de notas del estudiante con el pensum de destino y genera la resolución en Word.

| Dato | Valor |
|---|---|
| Versión | 1.0.0 (`pyproject.toml`, `APP_VERSION` en `app/core/config.py`) |
| Fecha | noviembre de 2026 |
| Commit registrado | el que figura en `ENTREGA.md` de la carpeta de entrega (este archivo no puede llevar su propio hash) |
| Autores | Bryan Yepes, Karen Mancilla Solarte, Zulema León Escobar y Jefferson Muñoz Luligo |
| Institución | Corporación Universitaria Autónoma del Cauca |
| Frontend | repositorio `homologaciones-frontend` |

## Requisitos

- Python 3.12 y [uv](https://docs.astral.sh/uv/)
- PostgreSQL 16
- Redis 7 (lista de tokens revocados)
- Docker y Docker Compose, si se quieren levantar PostgreSQL y Redis con `docker-compose.yml`
- Una clave de OpenAI para el análisis (modelo `gpt-4o-mini`)
- Opcionales: clave de Brevo (correos) y Cloudflare R2 (archivos). Sin ellas no se envían correos y los archivos quedan en `uploads/`

## Stack

FastAPI, SQLAlchemy 2 (asyncpg), Alembic, Pydantic 2, python-jose (JWT), bcrypt, OpenAI SDK, pypdf, docxtpl, httpx (Brevo), boto3 (R2). Versiones exactas en `uv.lock`.

## Roles

| Rol | Qué puede hacer |
|-----|----------------|
| Estudiante | Crear solicitudes, subir notas, enviarlas |
| Coordinador | Tomar solicitudes, subir el pensum de destino, activar y corregir el análisis IA, enviarlas al vicerrector |
| Vicerrector | Corregir asignaturas, aprobar o rechazar, generar la resolución |
| Admin | Gestionar usuarios y catálogos |

## Flujo de una solicitud

```
BORRADOR → ENVIADA → EN_REVISION → PROCESANDO_IA → REVISION_COORDINADOR → PENDIENTE_RECTOR → APROBADA / RECHAZADA
```

## Instalación local

```bash
git clone https://github.com/bryanypes/homologaciones-api
cd homologaciones-api
uv sync
cp .env.example .env
```

`docker-compose.yml` publica PostgreSQL en el puerto **5433** y Redis en el **6380**. Si se usan esos contenedores, en `.env` hay que cambiar `localhost:5432` por `localhost:5433` (en `DATABASE_URL` y `DATABASE_URL_ASYNC`) y `localhost:6379` por `localhost:6380`. También hay que poner `SECRET_KEY` y `OPENAI_API_KEY`.

```bash
docker compose up -d postgres redis
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

- Salud: `GET http://localhost:8000/health` → `{"status": "ok", "version": "1.0.0"}`
- Documentación: `http://localhost:8000/docs`

Para levantar todo con Docker (API incluida) ver [GUIA_DOCKER.md](GUIA_DOCKER.md).

## Variables de entorno

Ver `.env.example`. Obligatorias: `DATABASE_URL`, `DATABASE_URL_ASYNC`, `SECRET_KEY`, `OPENAI_API_KEY`. El resto tiene valor por defecto o es opcional.

## Usuarios iniciales (seed)

Al arrancar por primera vez se crean:

| Email | Password | Rol |
|-------|----------|-----|
| `admin@universidad.edu.co` | `Admin2024!` | Admin |
| `vicerrector@universidad.edu.co` | `Rector2024!` | Vicerrector |

En un despliegue real hay que cambiar estas contraseñas. El admin crea los coordinadores desde `POST /api/v1/usuarios/`; el registro público solo crea estudiantes.

## Pruebas

```bash
uv run pytest tests/ -v
```

Las pruebas usan SQLite en memoria y un Redis simulado, así que no necesitan servicios externos. El CI (`.github/workflows/ci.yml`) además aplica las migraciones sobre PostgreSQL 16 y construye la imagen Docker.

## Estructura

```
app/
├── main.py            # aplicación FastAPI, CORS, seed al arrancar
├── api/v1/            # rutas: auth, solicitudes, documentos, homologaciones, academico, usuarios
├── core/              # config, base de datos, seguridad, dependencias, seed
├── models/            # modelos SQLAlchemy (11 tablas)
├── schemas/           # contratos Pydantic
├── services/
│   ├── ai_service.py       # análisis con OpenAI
│   ├── doc_service.py      # resolución Word (docxtpl)
│   ├── email_service.py    # notificaciones (Brevo)
│   ├── storage_service.py  # R2 o disco local
│   └── kafka_service.py    # productor Kafka (no se usa en el flujo actual)
└── workers/           # consumidor Kafka (no se arranca en el flujo actual)
alembic/versions/      # 20 migraciones
templates/
├── plantilla_resolucion_matricula.docx
├── LOGO.png                # logo de los correos
└── Ia*.png, IA*.png        # mascota de los correos según el estado
tests/                 # pruebas de endpoints y de /health
scripts/reset-db.sh    # reinicia la base de desarrollo
```
