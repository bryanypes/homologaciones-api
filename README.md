# Sistema de Homologaciones — Uniautónoma del Cauca

Backend para gestión de solicitudes de homologación académica. Incluye análisis con IA y generación de resoluciones en Word.

## Stack

- **FastAPI** + Python 3.12
- **PostgreSQL** + Alembic
- **Redis** (blacklist de tokens JWT)
- **OpenAI GPT-4o-mini** (análisis de homologaciones)
- **docxtpl** (resoluciones Word desde plantilla oficial)
- **Brevo** (notificaciones por correo)
- **Cloudflare R2** (almacenamiento de archivos)
- **uv** (gestor de dependencias)

## Roles

| Rol | Qué puede hacer |
|-----|----------------|
| Estudiante | Crear solicitudes, subir notas, enviarlas |
| Coordinador | Revisar solicitudes, activar análisis IA |
| Vicerrector | Aprobar/rechazar, generar resolución Word |
| Admin | Gestionar usuarios y programas/pensum |

## Flujo de una solicitud

```
BORRADOR → ENVIADA → EN_REVISION → PROCESANDO_IA → PENDIENTE_RECTOR → APROBADA / RECHAZADA
```

1. Estudiante crea la solicitud y sube su certificado de notas
2. Coordinador la toma, sube el pensum destino y activa la IA
3. GPT-4o-mini analiza los PDFs y genera la tabla de homologación
4. Vicerrector revisa y aprueba o rechaza
5. Se genera la resolución oficial en Word

## Instalación local

```bash
git clone https://github.com/bryanypes/homologaciones-api
cd homologaciones-api

uv sync

cp .env.example .env
# editar .env con tus valores

docker compose up -d postgres redis
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

La API queda en `http://localhost:8000/docs`

## Variables de entorno

Ver `.env.example`. Las mínimas para correr:

- `DATABASE_URL` / `DATABASE_URL_ASYNC`
- `SECRET_KEY` (cualquier string largo)
- `OPENAI_API_KEY`

El correo y R2 son opcionales — si no se configuran el sistema funciona igual, sin enviar notificaciones ni guardar archivos en la nube.

## Usuarios iniciales (seed)

Al arrancar por primera vez se crean automáticamente:

| Email | Password | Rol |
|-------|----------|-----|
| `admin@universidad.edu.co` | `Admin2024!` | Admin |
| `vicerrector@universidad.edu.co` | `Rector2024!` | Vicerrector |

El admin puede crear coordinadores desde `POST /api/v1/usuarios/`. El registro público solo acepta estudiantes.

## Tests

```bash
uv run pytest tests/ -v
```

## Estructura

```
app/
├── api/v1/          # Endpoints
├── core/            # Config, DB, seguridad, seed
├── models/          # SQLAlchemy
├── schemas/         # Pydantic
├── services/
│   ├── ai_service.py       # Análisis con OpenAI
│   ├── doc_service.py      # Resolución Word (docxtpl)
│   ├── email_service.py    # Notificaciones (Brevo)
│   └── storage_service.py  # R2 / disco local
templates/
├── plantilla_resolucion_matricula.docx
├── LOGO.png                # Logo fijo en el header de los correos
├── Iaaprobada.png          # Mascota — solicitud aprobada
├── Iaerror.png             # Mascota — solicitud rechazada
├── Iapensando.png          # Mascota — procesando / en revisión / pendiente rector
├── IAsaludando.png         # Mascota — solicitud enviada / borrador
└── IAseñalandoderecha.png  # Mascota — recuperación de contraseña
```
