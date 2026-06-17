import sys
import os
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Motor SQLite en memoria ────────────────────────────────────
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)

TestSessionLocal = sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── Override de get_db ─────────────────────────────────────────
async def override_get_db():
    async with TestSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Datos de test ──────────────────────────────────────────────
RECTOR_EMAIL = "rector@universidad.edu.co"
RECTOR_PASSWORD = "Rector2024!"

ESTUDIANTE = {
    "nombre": "Carlos",
    "apellido": "Test",
    "password": "Test1234!",
    "rol": "estudiante",
}
COORDINADOR = {
    "nombre": "Ana",
    "apellido": "Coordinadora",
    "password": "Test1234!",
    "rol": "coordinador",
}


# ── App con overrides ──────────────────────────────────────────
@pytest.fixture(scope="session")
def app_test():
    """
    Crea la app FastAPI con:
    - DB sobreescrita a SQLite en memoria
    - Redis mockeado (fakeredis o AsyncMock)
    - Kafka mockeado
    - Lifespan reemplazado para no conectar a servicios externos
    """
    _blacklist: dict = {}

    fake_redis = AsyncMock()
    fake_redis.get = AsyncMock(side_effect=lambda key: _blacklist.get(key))
    fake_redis.setex = AsyncMock(side_effect=lambda key, ttl, val: _blacklist.update({key: val}))
    fake_redis.delete = AsyncMock(side_effect=lambda key: _blacklist.pop(key, None))
    fake_redis.aclose = AsyncMock()

    # FIX: publicar_cambio_estado y publicar_homologacion_completada son funciones
    # síncronas — deben mockearse con MagicMock, no AsyncMock.
    with patch("app.workers.homologacion_worker.iniciar_worker_en_background", return_value=None), \
         patch("app.core.deps.aioredis.from_url", return_value=fake_redis), \
         patch("app.services.kafka_service.publicar_cambio_estado", new_callable=MagicMock), \
         patch("app.services.kafka_service.publicar_homologacion_completada", new_callable=MagicMock):

        from app.main import app
        from app.core.database import Base, get_db

        app.dependency_overrides[get_db] = override_get_db

        yield app

        app.dependency_overrides.clear()


@pytest.fixture(scope="session")
async def setup_db(app_test):
    """Crea todas las tablas en SQLite y crea el rector inicial."""
    from app.core.database import Base
    from app.models.usuario import Usuario, Rol
    from app.core.security import hash_password

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestSessionLocal() as db:
        rector = Usuario(
            nombre="Pedro",
            apellido="Rector",
            email=RECTOR_EMAIL,
            password_hash=hash_password(RECTOR_PASSWORD),
            rol=Rol.RECTOR,
            activo=True,
        )
        db.add(rector)
        await db.commit()

    yield

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(scope="session")
async def client(app_test, setup_db):
    async with AsyncClient(
        transport=ASGITransport(app=app_test), base_url="http://test"
    ) as ac:
        yield ac


# ── Helpers de autenticación ───────────────────────────────────
async def _login(client: AsyncClient, email: str, password: str) -> str:
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"Login falló para {email}: {resp.text}"
    return resp.json()["access_token"]


async def _registrar_estudiante(client: AsyncClient, datos: dict) -> str:
    email = f"{uuid4().hex[:8]}@test.com"
    resp = await client.post("/api/v1/auth/register", json={**datos, "email": email})
    assert resp.status_code == 201, f"Registro falló: {resp.text}"
    token = await _login(client, email, datos["password"])
    return token


# ── Tokens ─────────────────────────────────────────────────────
@pytest.fixture(scope="session")
async def token_rector(client: AsyncClient) -> str:
    return await _login(client, RECTOR_EMAIL, RECTOR_PASSWORD)


@pytest.fixture(scope="session")
async def token_estudiante(client: AsyncClient) -> str:
    return await _registrar_estudiante(client, ESTUDIANTE)


@pytest.fixture(scope="session")
async def token_estudiante2(client: AsyncClient) -> str:
    return await _registrar_estudiante(client, ESTUDIANTE)


@pytest.fixture(scope="session")
async def token_coordinador(client: AsyncClient, token_rector: str) -> str:
    email = f"coord_{uuid4().hex[:8]}@test.com"
    resp = await client.post(
        "/api/v1/usuarios/",
        headers={"Authorization": f"Bearer {token_rector}"},
        json={**COORDINADOR, "email": email},
    )
    assert resp.status_code == 201, f"Crear coordinador falló: {resp.text}"
    return await _login(client, email, COORDINADOR["password"])


# ── Solicitudes ────────────────────────────────────────────────
_SOL_BASE = {
    "institucion_origen": "SENA",
    "programa_origen": "ADSI",
    "institucion_destino": "Unicauca",
    "programa_destino": "Ingeniería de Sistemas",
}


@pytest.fixture(scope="session")
async def solicitud_id(client: AsyncClient, token_estudiante: str) -> str:
    """Solicitud en estado borrador, sin PDFs — para tests de acceso y documentos."""
    resp = await client.post(
        "/api/v1/solicitudes/",
        headers={"Authorization": f"Bearer {token_estudiante}"},
        json=_SOL_BASE,
    )
    assert resp.status_code == 201, f"Crear solicitud falló: {resp.text}"
    return resp.json()["id"]


@pytest.fixture(scope="session")
async def solicitud_enviada_id(client: AsyncClient, token_estudiante: str) -> str:
    """Solicitud separada con PDFs subidos y enviada — para tests de flujo."""
    crear = await client.post(
        "/api/v1/solicitudes/",
        headers={"Authorization": f"Bearer {token_estudiante}"},
        json=_SOL_BASE,
    )
    assert crear.status_code == 201, f"Crear solicitud enviada falló: {crear.text}"
    sid = crear.json()["id"]

    pdf = b"%PDF-1.4 fake pdf content"
    for tipo in ("pensum-origen", "pensum-destino"):
        up = await client.post(
            f"/api/v1/documentos/{sid}/{tipo}",
            headers={"Authorization": f"Bearer {token_estudiante}"},
            files={"file": ("test.pdf", pdf, "application/pdf")},
        )
        assert up.status_code == 201, f"Subir {tipo} falló: {up.text}"

    enviar = await client.patch(
        f"/api/v1/solicitudes/{sid}/enviar",
        headers={"Authorization": f"Bearer {token_estudiante}"},
    )
    assert enviar.status_code == 200, f"Enviar solicitud falló: {enviar.text}"
    return sid