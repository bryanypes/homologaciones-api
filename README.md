# Sistema de Homologaciones Académicas — Uniautónoma del Cauca

Backend para gestión y procesamiento automatizado de solicitudes de homologación académica universitaria, con análisis por inteligencia artificial y generación de resoluciones oficiales.

## Stack tecnológico

| Capa | Tecnología |
|------|-----------|
| Framework | FastAPI + Python 3.12 |
| Base de datos | PostgreSQL 16 + Alembic |
| Caché / Blacklist JWT | Redis 7 |
| Eventos / Notificaciones | Kafka |
| IA | OpenAI GPT-4o-mini |
| Generación de documentos | python-docx (Node.js) |
| Notificaciones email | aiosmtplib |
| Contenedores | Docker + Docker Compose |
| CI/CD | GitHub Actions |
| Gestor de dependencias | uv |

## Roles y permisos

| Rol | Acciones |
|-----|---------|
| **Estudiante** | Crear solicitudes, subir certificado de notas, enviar solicitud, ver sus solicitudes |
| **Coordinador** | Tomar solicitudes en revisión, subir pensum destino, activar procesamiento IA, listar usuarios |
| **Rector** | Aprobar o rechazar homologaciones, generar resolución Word, gestionar usuarios |

## Flujo completo

```
1. Estudiante crea solicitud (con cédula, teléfono, correo)
2. Estudiante sube certificado de notas (PDF)
3. Estudiante envía la solicitud
4. Coordinador toma la solicitud en revisión
5. Coordinador sube el pensum del programa destino (PDF)
6. Coordinador activa el procesamiento con IA
7. GPT-4o-mini analiza ambos PDFs y genera tabla de homologaciones
8. Rector revisa, aprueba o rechaza
9. Rector descarga la resolución oficial en Word
```

### Estados de una solicitud

```
BORRADOR → ENVIADA → EN_REVISION → PROCESANDO_IA → PENDIENTE_RECTOR → APROBADA / RECHAZADA
```

## Requisitos

- Docker Desktop corriendo
- Python 3.12+
- uv (`pip install uv`)

## Instalación local (desarrollo)

```bash
# 1. Clonar
git clone https://github.com/tu-usuario/homologaciones-api
cd homologaciones-api

# 2. Instalar dependencias
uv sync
uv add aiosmtplib pypdf

# 3. Configurar variables de entorno
cp .env.example .env
# Editar .env con tus valores

# 4. Levantar servicios
docker compose up -d postgres redis kafka

# 5. Correr migraciones
uv run alembic upgrade head

# 6. Arrancar la API
uv run uvicorn app.main:app --reload
```

El seed carga automáticamente al arrancar: países, departamentos, municipios, instituciones, facultades, programas y el usuario rector inicial.

## Instalación con Docker (producción)

```bash
cp .env.example .env.docker
# Editar .env.docker con hostnames Docker (postgres, redis, kafka)

docker compose up
```

## Variables de entorno

| Variable | Descripción | Ejemplo |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL sync (Alembic) | `postgresql://dev:dev@localhost:5433/homologaciones` |
| `DATABASE_URL_ASYNC` | PostgreSQL async (app) | `postgresql+asyncpg://dev:dev@localhost:5433/homologaciones` |
| `REDIS_URL` | Redis | `redis://localhost:6380` |
| `SECRET_KEY` | Clave para firmar JWT | `cambia_esto_en_produccion` |
| `ALGORITHM` | Algoritmo JWT | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Expiración del token | `60` |
| `OPENAI_API_KEY` | API key de OpenAI | `sk-...` |
| `KAFKA_BOOTSTRAP_SERVERS` | Servidor Kafka | `localhost:9092` |
| `UPLOAD_DIR` | Directorio de PDFs subidos | `uploads` |
| `MAX_FILE_SIZE_MB` | Tamaño máximo de PDF | `10` |
| `SMTP_HOST` | Servidor SMTP para emails | `smtp.gmail.com` |
| `SMTP_PORT` | Puerto SMTP | `587` |
| `SMTP_USER` | Usuario SMTP | `notif@universidad.edu.co` |
| `SMTP_PASSWORD` | Contraseña SMTP | `...` |
| `EMAIL_FROM` | Remitente de notificaciones | `no-reply@universidad.edu.co` |

> Si `SMTP_HOST` no está configurado, el sistema funciona normalmente sin enviar emails.

## Usuario inicial (seed)

Al arrancar por primera vez se crea automáticamente:

| Campo | Valor |
|-------|-------|
| Email | `rector@universidad.edu.co` |
| Password | `Rector2024!` |
| Rol | `rector` |

El rector puede crear coordinadores desde `POST /api/v1/usuarios/`. El registro público (`POST /api/v1/auth/register`) solo acepta rol `estudiante`.

## Endpoints principales

### Autenticación
| Método | Ruta | Acceso | Descripción |
|--------|------|--------|-------------|
| POST | `/api/v1/auth/register` | Público | Registro (solo estudiantes) |
| POST | `/api/v1/auth/login` | Público | Login, retorna JWT |
| POST | `/api/v1/auth/logout` | Autenticado | Invalida el token (blacklist Redis) |
| GET | `/api/v1/auth/me` | Autenticado | Perfil del usuario actual |
| PATCH | `/api/v1/auth/me` | Autenticado | Actualizar perfil |

### Usuarios
| Método | Ruta | Acceso | Descripción |
|--------|------|--------|-------------|
| GET | `/api/v1/usuarios/` | Coordinador, Rector | Listar usuarios (paginado, con filtros) |
| POST | `/api/v1/usuarios/` | Rector | Crear coordinador o rector |
| PATCH | `/api/v1/usuarios/{id}/activar` | Rector | Activar cuenta |
| PATCH | `/api/v1/usuarios/{id}/desactivar` | Rector | Desactivar cuenta |
| PATCH | `/api/v1/usuarios/{id}/rol` | Rector | Cambiar rol |

### Solicitudes
| Método | Ruta | Acceso | Descripción |
|--------|------|--------|-------------|
| POST | `/api/v1/solicitudes/` | Estudiante | Crear solicitud |
| GET | `/api/v1/solicitudes/` | Todos | Listar (filtros: estado, fecha, programa) |
| GET | `/api/v1/solicitudes/{id}` | Todos | Detalle de solicitud |
| GET | `/api/v1/solicitudes/{id}/historial` | Todos | Historial de estados |
| PATCH | `/api/v1/solicitudes/{id}/enviar` | Estudiante | Enviar solicitud (requiere notas subidas) |
| PATCH | `/api/v1/solicitudes/{id}/revisar` | Coordinador | Tomar en revisión |
| PATCH | `/api/v1/solicitudes/{id}/aprobar` | Rector | Aprobar homologación |
| PATCH | `/api/v1/solicitudes/{id}/rechazar` | Rector | Rechazar homologación |

### Documentos
| Método | Ruta | Acceso | Descripción |
|--------|------|--------|-------------|
| POST | `/api/v1/documentos/{id}/notas` | Estudiante | Subir certificado de notas (PDF) |
| POST | `/api/v1/documentos/{id}/pensum-destino` | Coordinador | Subir pensum del programa destino (PDF) |
| GET | `/api/v1/documentos/{id}` | Todos | Listar documentos de una solicitud |
| GET | `/api/v1/documentos/{id}/{doc_id}/descargar` | Todos | Descargar PDF |

### Homologaciones
| Método | Ruta | Acceso | Descripción |
|--------|------|--------|-------------|
| POST | `/api/v1/homologaciones/{id}/procesar` | Coordinador | Activar análisis con IA |
| GET | `/api/v1/homologaciones/{id}` | Coordinador, Rector | Ver resultado del análisis |
| POST | `/api/v1/homologaciones/{id}/generar-resolucion` | Rector | Descargar resolución Word |

### Catálogos y Académico
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/v1/catalogos/paises` | Países |
| GET | `/api/v1/catalogos/departamentos` | Departamentos por país |
| GET | `/api/v1/catalogos/municipios` | Municipios por departamento |
| GET | `/api/v1/instituciones` | Instituciones |
| GET | `/api/v1/facultades` | Facultades por institución |
| GET | `/api/v1/programas` | Programas por facultad |

Documentación interactiva: `http://localhost:8000/docs`

## Tests

```bash
uv run pytest tests/ -v --tb=short
```

## Estructura del proyecto

```
homologaciones-api/
├── app/
│   ├── api/v1/
│   │   ├── auth.py           # Registro, login, logout, perfil
│   │   ├── solicitudes.py    # CRUD + flujo de estados
│   │   ├── documentos.py     # Subida y descarga de PDFs
│   │   ├── homologaciones.py # Procesamiento IA + resolución Word
│   │   ├── usuarios.py       # CRUD usuarios (coordinador/rector)
│   │   ├── catalogos.py      # Países, departamentos, municipios
│   │   └── academico.py      # Instituciones, facultades, programas
│   ├── core/
│   │   ├── config.py         # Settings con Pydantic V2
│   │   ├── database.py       # AsyncSession + Base
│   │   ├── deps.py           # get_current_user, require_rol
│   │   ├── security.py       # bcrypt, JWT
│   │   └── seed.py           # Carga inicial de datos
│   ├── models/               # Modelos SQLAlchemy
│   ├── schemas/              # Schemas Pydantic
│   ├── services/
│   │   ├── ai_service.py     # OpenAI GPT-4o-mini
│   │   ├── doc_service.py    # Generación resolución Word
│   │   ├── email_service.py  # Notificaciones SMTP
│   │   └── kafka_service.py  # Publicación de eventos
│   └── workers/
│       └── homologacion_worker.py  # Consumidor Kafka (emails)
├── templates/
│   └── resolucion_plantilla.docx   # Plantilla oficial Word
├── tests/
├── alembic/
├── docker-compose.yml
├── Dockerfile
└── pyproject.toml
```

## Datos precargados (seed)

**5 instituciones del Cauca:**
- Corporación Universitaria Autónoma del Cauca
- SENA Regional Cauca
- Colegio Mayor del Cauca
- Fundación Universitaria de Popayán (FUP)
- Universidad del Cauca

**23 programas académicos** distribuidos en 5 facultades.

## Notas de producción

- Los tokens JWT invalidados se almacenan en Redis con TTL igual al tiempo de expiración.
- Las migraciones corren automáticamente antes de uvicorn en el Dockerfile.
- Kafka corre en modo KRaft (sin Zookeeper).
- Los PDFs se almacenan en el volumen `uploads/` — en producción usar S3 o almacenamiento persistente equivalente.
- El email es opcional: si no se configura SMTP, el sistema opera normalmente y loguea un warning.