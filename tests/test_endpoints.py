import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4


# ──────────────────────────────────────────────────────────────
# Fixtures de usuarios
# ──────────────────────────────────────────────────────────────

ESTUDIANTE = {
    "nombre": "Carlos",
    "apellido": "Test",
    "email": f"estudiante_{uuid4().hex[:6]}@test.com",
    "password": "Test1234!",
    "rol": "estudiante",
}

COORDINADOR = {
    "nombre": "Ana",
    "apellido": "Coordinadora",
    "email": f"coordinador_{uuid4().hex[:6]}@test.com",
    "password": "Test1234!",
    "rol": "coordinador",
}

RECTOR = {
    "nombre": "Pedro",
    "apellido": "Rector",
    "email": f"rector_{uuid4().hex[:6]}@test.com",
    "password": "Test1234!",
    "rol": "rector",
}


async def _registrar_y_login(client: AsyncClient, datos: dict) -> str:
    """Helper: registra un usuario y retorna su token. Para roles no-estudiante usa /usuarios/."""
    if datos["rol"] == "estudiante":
        await client.post("/api/v1/auth/register", json=datos)
    # Para otros roles asumimos que ya existen (creados por el rector en setup)
    resp = await client.post("/api/v1/auth/login", json={
        "email": datos["email"],
        "password": datos["password"],
    })
    assert resp.status_code == 200, f"Login falló: {resp.text}"
    return resp.json()["access_token"]


# ──────────────────────────────────────────────────────────────
# Auth
# ──────────────────────────────────────────────────────────────

class TestAuth:

    async def test_register_estudiante_ok(self, client: AsyncClient):
        datos = {**ESTUDIANTE, "email": f"e_{uuid4().hex[:6]}@test.com"}
        resp = await client.post("/api/v1/auth/register", json=datos)
        assert resp.status_code == 201
        assert resp.json()["rol"] == "estudiante"

    async def test_register_coordinador_bloqueado(self, client: AsyncClient):
        """El registro público no debe permitir crear coordinadores."""
        datos = {**COORDINADOR, "email": f"c_{uuid4().hex[:6]}@test.com"}
        resp = await client.post("/api/v1/auth/register", json=datos)
        assert resp.status_code == 400
        assert "estudiante" in resp.json()["detail"].lower()

    async def test_register_rector_bloqueado(self, client: AsyncClient):
        datos = {**RECTOR, "email": f"r_{uuid4().hex[:6]}@test.com"}
        resp = await client.post("/api/v1/auth/register", json=datos)
        assert resp.status_code == 400

    async def test_register_email_duplicado(self, client: AsyncClient):
        datos = {**ESTUDIANTE, "email": f"dup_{uuid4().hex[:6]}@test.com"}
        await client.post("/api/v1/auth/register", json=datos)
        resp = await client.post("/api/v1/auth/register", json=datos)
        assert resp.status_code == 400

    async def test_login_ok(self, client: AsyncClient):
        email = f"login_{uuid4().hex[:6]}@test.com"
        await client.post("/api/v1/auth/register", json={**ESTUDIANTE, "email": email})
        resp = await client.post("/api/v1/auth/login", json={"email": email, "password": ESTUDIANTE["password"]})
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    async def test_login_password_incorrecta(self, client: AsyncClient):
        email = f"wrong_{uuid4().hex[:6]}@test.com"
        await client.post("/api/v1/auth/register", json={**ESTUDIANTE, "email": email})
        resp = await client.post("/api/v1/auth/login", json={"email": email, "password": "incorrecta"})
        assert resp.status_code == 401

    async def test_logout_invalida_token(self, client: AsyncClient):
        email = f"logout_{uuid4().hex[:6]}@test.com"
        await client.post("/api/v1/auth/register", json={**ESTUDIANTE, "email": email})
        login = await client.post("/api/v1/auth/login", json={"email": email, "password": ESTUDIANTE["password"]})
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post("/api/v1/auth/logout", headers=headers)
        assert resp.status_code == 204

        # El token en blacklist debe rechazarse
        resp2 = await client.get("/api/v1/auth/me", headers=headers)
        assert resp2.status_code == 401

    async def test_token_invalido_rechazado(self, client: AsyncClient):
        resp = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer token_falso_xyz"})
        assert resp.status_code == 401

    async def test_sin_token_rechazado(self, client: AsyncClient):
        resp = await client.get("/api/v1/solicitudes/")
        assert resp.status_code in (401, 403)


# ──────────────────────────────────────────────────────────────
# Control de acceso por rol
# ──────────────────────────────────────────────────────────────

class TestControlAcceso:

    async def test_estudiante_no_puede_revisar(self, client: AsyncClient, token_estudiante: str, solicitud_id: str):
        resp = await client.patch(
            f"/api/v1/solicitudes/{solicitud_id}/revisar",
            headers={"Authorization": f"Bearer {token_estudiante}"},
            json={"observacion": "intento"},
        )
        assert resp.status_code == 403

    async def test_estudiante_no_puede_aprobar(self, client: AsyncClient, token_estudiante: str, solicitud_id: str):
        resp = await client.patch(
            f"/api/v1/solicitudes/{solicitud_id}/aprobar",
            headers={"Authorization": f"Bearer {token_estudiante}"},
            json={"observacion": "intento"},
        )
        assert resp.status_code == 403

    async def test_coordinador_no_puede_aprobar(self, client: AsyncClient, token_coordinador: str, solicitud_id: str):
        resp = await client.patch(
            f"/api/v1/solicitudes/{solicitud_id}/aprobar",
            headers={"Authorization": f"Bearer {token_coordinador}"},
            json={"observacion": "intento"},
        )
        assert resp.status_code == 403

    async def test_estudiante_no_ve_solicitud_ajena(self, client: AsyncClient, token_estudiante2: str, solicitud_id: str):
        """Estudiante B no puede ver la solicitud del estudiante A."""
        resp = await client.get(
            f"/api/v1/solicitudes/{solicitud_id}",
            headers={"Authorization": f"Bearer {token_estudiante2}"},
        )
        assert resp.status_code == 403

    async def test_coordinador_no_puede_crear_usuarios(self, client: AsyncClient, token_coordinador: str):
        resp = await client.post(
            "/api/v1/usuarios/",
            headers={"Authorization": f"Bearer {token_coordinador}"},
            json={**ESTUDIANTE, "email": f"x_{uuid4().hex[:6]}@test.com"},
        )
        assert resp.status_code == 403


# ──────────────────────────────────────────────────────────────
# Solicitudes
# ──────────────────────────────────────────────────────────────

class TestSolicitudes:

    async def test_crear_solicitud(self, client: AsyncClient, token_estudiante: str):
        resp = await client.post(
            "/api/v1/solicitudes/",
            headers={"Authorization": f"Bearer {token_estudiante}"},
            json={
                "institucion_origen": "SENA",
                "programa_origen": "ADSI",
                "institucion_destino": "Unicauca",
                "programa_destino": "Ingeniería de Sistemas",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["estado"] == "borrador"

    async def test_enviar_sin_pdfs_falla(self, client: AsyncClient, token_estudiante: str):
        """Enviar sin subir PDFs debe retornar 400."""
        # Crear nueva solicitud limpia
        crear = await client.post(
            "/api/v1/solicitudes/",
            headers={"Authorization": f"Bearer {token_estudiante}"},
            json={
                "institucion_origen": "SENA",
                "programa_origen": "ADSI",
                "institucion_destino": "Unicauca",
                "programa_destino": "Ingeniería de Sistemas",
            },
        )
        sol_id = crear.json()["id"]

        resp = await client.patch(
            f"/api/v1/solicitudes/{sol_id}/enviar",
            headers={"Authorization": f"Bearer {token_estudiante}"},
        )
        assert resp.status_code == 400
        assert "falt" in resp.json()["detail"].lower()

    async def test_enviar_doble_falla(self, client: AsyncClient, token_estudiante: str, solicitud_enviada_id: str):
        """Enviar una solicitud ya enviada debe retornar 400."""
        resp = await client.patch(
            f"/api/v1/solicitudes/{solicitud_enviada_id}/enviar",
            headers={"Authorization": f"Bearer {token_estudiante}"},
        )
        assert resp.status_code == 400

    async def test_paginacion_solicitudes(self, client: AsyncClient, token_coordinador: str):
        resp = await client.get(
            "/api/v1/solicitudes/?page=1&size=5",
            headers={"Authorization": f"Bearer {token_coordinador}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "total" in body
        assert "items" in body
        assert "page" in body
        assert len(body["items"]) <= 5

    async def test_filtro_por_estado(self, client: AsyncClient, token_coordinador: str):
        resp = await client.get(
            "/api/v1/solicitudes/?estado=borrador",
            headers={"Authorization": f"Bearer {token_coordinador}"},
        )
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert item["estado"] == "borrador"

    async def test_historial_estados(self, client: AsyncClient, token_estudiante: str, solicitud_enviada_id: str):
        resp = await client.get(
            f"/api/v1/solicitudes/{solicitud_enviada_id}/historial",
            headers={"Authorization": f"Bearer {token_estudiante}"},
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        assert len(resp.json()) >= 1


# ──────────────────────────────────────────────────────────────
# Documentos
# ──────────────────────────────────────────────────────────────

class TestDocumentos:

    async def test_subir_pdf_ok(self, client: AsyncClient, token_estudiante: str, solicitud_id: str):
        pdf_bytes = b"%PDF-1.4 fake pdf content for testing"
        resp = await client.post(
            f"/api/v1/documentos/{solicitud_id}/pensum-origen",
            headers={"Authorization": f"Bearer {token_estudiante}"},
            files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
        )
        assert resp.status_code == 201
        assert resp.json()["tipo"] == "pensum_origen"

    async def test_subir_no_pdf_falla(self, client: AsyncClient, token_estudiante: str, solicitud_id: str):
        resp = await client.post(
            f"/api/v1/documentos/{solicitud_id}/pensum-origen",
            headers={"Authorization": f"Bearer {token_estudiante}"},
            files={"file": ("test.jpg", b"fake image", "image/jpeg")},
        )
        assert resp.status_code == 400

    async def test_subir_pdf_otro_estudiante_falla(
        self, client: AsyncClient, token_estudiante2: str, solicitud_id: str
    ):
        pdf_bytes = b"%PDF-1.4 fake"
        resp = await client.post(
            f"/api/v1/documentos/{solicitud_id}/pensum-origen",
            headers={"Authorization": f"Bearer {token_estudiante2}"},
            files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
        )
        assert resp.status_code == 403

    async def test_listar_documentos(self, client: AsyncClient, token_estudiante: str, solicitud_id: str):
        resp = await client.get(
            f"/api/v1/documentos/{solicitud_id}",
            headers={"Authorization": f"Bearer {token_estudiante}"},
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


# ──────────────────────────────────────────────────────────────
# Usuarios (CRUD)
# ──────────────────────────────────────────────────────────────

class TestUsuarios:

    async def test_rector_crea_coordinador(self, client: AsyncClient, token_rector: str):
        email = f"coord_{uuid4().hex[:6]}@test.com"
        resp = await client.post(
            "/api/v1/usuarios/",
            headers={"Authorization": f"Bearer {token_rector}"},
            json={**COORDINADOR, "email": email},
        )
        assert resp.status_code == 201
        assert resp.json()["rol"] == "coordinador"

    async def test_rector_lista_usuarios(self, client: AsyncClient, token_rector: str):
        resp = await client.get(
            "/api/v1/usuarios/",
            headers={"Authorization": f"Bearer {token_rector}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "total" in body
        assert "items" in body

    async def test_filtro_por_rol(self, client: AsyncClient, token_rector: str):
        resp = await client.get(
            "/api/v1/usuarios/?rol=estudiante",
            headers={"Authorization": f"Bearer {token_rector}"},
        )
        assert resp.status_code == 200
        for u in resp.json()["items"]:
            assert u["rol"] == "estudiante"

    async def test_rector_desactiva_usuario(self, client: AsyncClient, token_rector: str):
        # Crear usuario
        email = f"deact_{uuid4().hex[:6]}@test.com"
        crear = await client.post(
            "/api/v1/usuarios/",
            headers={"Authorization": f"Bearer {token_rector}"},
            json={**ESTUDIANTE, "email": email},
        )
        uid = crear.json()["id"]

        resp = await client.patch(
            f"/api/v1/usuarios/{uid}/desactivar",
            headers={"Authorization": f"Bearer {token_rector}"},
        )
        assert resp.status_code == 200
        assert resp.json()["activo"] is False

        # Verificar que no puede iniciar sesión
        login = await client.post("/api/v1/auth/login", json={"email": email, "password": ESTUDIANTE["password"]})
        assert login.status_code == 403

    async def test_rector_no_puede_desactivarse_a_si_mismo(self, client: AsyncClient, token_rector: str):
        me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_rector}"})
        uid = me.json()["id"]
        resp = await client.patch(
            f"/api/v1/usuarios/{uid}/desactivar",
            headers={"Authorization": f"Bearer {token_rector}"},
        )
        assert resp.status_code == 400

    async def test_estudiante_no_accede_a_usuarios(self, client: AsyncClient, token_estudiante: str):
        resp = await client.get(
            "/api/v1/usuarios/",
            headers={"Authorization": f"Bearer {token_estudiante}"},
        )
        assert resp.status_code == 403


# ──────────────────────────────────────────────────────────────
# Email service (unit test con mock)
# ──────────────────────────────────────────────────────────────

class TestEmailService:

    @patch("app.services.email_service.settings")
    async def test_email_no_enviado_si_smtp_no_configurado(self, mock_settings):
        from app.services.email_service import notificar_cambio_estado
        mock_settings.SMTP_HOST = None
        mock_settings.SMTP_USER = None
        mock_settings.SMTP_PASSWORD = None
        mock_settings.EMAIL_FROM = None

        # No debe lanzar excepción, solo logear warning
        await notificar_cambio_estado(
            email_estudiante="test@test.com",
            nombre_estudiante="Test",
            solicitud_id=str(uuid4()),
            estado_anterior="borrador",
            estado_nuevo="enviada",
        )

    @patch("app.services.email_service.aiosmtplib")
    @patch("app.services.email_service.settings")
    async def test_email_enviado_con_smtp_configurado(self, mock_settings, mock_smtp):
        from app.services.email_service import notificar_cambio_estado
        mock_settings.SMTP_HOST = "smtp.test.com"
        mock_settings.SMTP_PORT = 587
        mock_settings.SMTP_USER = "user@test.com"
        mock_settings.SMTP_PASSWORD = "pass"
        mock_settings.EMAIL_FROM = "no-reply@test.com"
        mock_smtp.send = AsyncMock()

        await notificar_cambio_estado(
            email_estudiante="estudiante@test.com",
            nombre_estudiante="Carlos",
            solicitud_id=str(uuid4()),
            estado_anterior="borrador",
            estado_nuevo="enviada",
        )
        mock_smtp.send.assert_called_once()