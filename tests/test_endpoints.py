"""
Tests de integración para el sistema de homologaciones.

Ejecutar: uv run pytest tests/ -v

Requiere conftest.py con:
  - fixture `client`: AsyncClient con la app
  - fixture `db_session`: sesión de test con rollback
  - override de get_db
"""

import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4
import io


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def fake_pdf() -> bytes:
    """PDF mínimo válido para tests."""
    return b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\nxref\n0 1\n0000000000 65535 f\ntrailer\n<< /Size 1 /Root 1 0 R >>\nstartxref\n9\n%%EOF"


async def _registrar_estudiante(client: AsyncClient, email: str) -> str:
    """Registra un estudiante y retorna su token."""
    await client.post("/api/v1/auth/register", json={
        "nombre": "Test", "apellido": "User",
        "email": email, "password": "123456", "rol": "estudiante"
    })
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": "123456"})
    return r.json()["access_token"]


async def _login_rector(client: AsyncClient) -> str:
    r = await client.post("/api/v1/auth/login", json={
        "email": "rector@universidad.edu.co", "password": "Rector2024!"
    })
    assert r.status_code == 200, "El seed del rector no corrió"
    return r.json()["access_token"]


async def _crear_coordinador_y_login(client: AsyncClient, token_rector: str, email: str) -> str:
    await client.post("/api/v1/usuarios/", headers={"Authorization": f"Bearer {token_rector}"},
        json={"nombre": "Coord", "apellido": "Test", "email": email, "password": "Coord2024!", "rol": "coordinador"})
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": "Coord2024!"})
    return r.json()["access_token"]


async def _crear_solicitud(client: AsyncClient, token: str) -> str:
    r = await client.post("/api/v1/solicitudes/",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "cedula": "1061529242", "telefono": "3148757616",
            "correo_contacto": "test@test.com",
            "institucion_origen": "SENA", "programa_origen": "ADSI",
            "institucion_destino": "Uniautónoma", "programa_destino": "Ing. Software"
        })
    assert r.status_code == 201
    return r.json()["id"]


async def _subir_notas(client: AsyncClient, token: str, solicitud_id: str) -> str:
    r = await client.post(
        f"/api/v1/documentos/{solicitud_id}/notas",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("notas.pdf", fake_pdf(), "application/pdf")}
    )
    assert r.status_code == 201
    return r.json()["id"]


async def _subir_pensum_destino(client: AsyncClient, token: str, solicitud_id: str) -> str:
    r = await client.post(
        f"/api/v1/documentos/{solicitud_id}/pensum-destino",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("pensum.pdf", fake_pdf(), "application/pdf")}
    )
    assert r.status_code == 201
    return r.json()["id"]


# ──────────────────────────────────────────────────────────────────────────────
# Auth
# ──────────────────────────────────────────────────────────────────────────────

class TestAuth:

    async def test_register_estudiante_ok(self, client: AsyncClient):
        email = f"e_{uuid4().hex[:6]}@test.com"
        r = await client.post("/api/v1/auth/register", json={
            "nombre": "Test", "apellido": "User", "email": email,
            "password": "123456", "rol": "estudiante"
        })
        assert r.status_code == 201
        assert r.json()["rol"] == "estudiante"

    async def test_register_coordinador_bloqueado(self, client: AsyncClient):
        r = await client.post("/api/v1/auth/register", json={
            "nombre": "X", "apellido": "Y", "email": f"c_{uuid4().hex[:6]}@test.com",
            "password": "123456", "rol": "coordinador"
        })
        assert r.status_code == 400
        assert "estudiante" in r.json()["detail"].lower()

    async def test_register_rector_bloqueado(self, client: AsyncClient):
        r = await client.post("/api/v1/auth/register", json={
            "nombre": "X", "apellido": "Y", "email": f"r_{uuid4().hex[:6]}@test.com",
            "password": "123456", "rol": "rector"
        })
        assert r.status_code == 400

    async def test_register_email_duplicado(self, client: AsyncClient):
        email = f"dup_{uuid4().hex[:6]}@test.com"
        await _registrar_estudiante(client, email)
        r = await client.post("/api/v1/auth/register", json={
            "nombre": "X", "apellido": "Y", "email": email,
            "password": "123456", "rol": "estudiante"
        })
        assert r.status_code == 400

    async def test_login_ok(self, client: AsyncClient):
        email = f"login_{uuid4().hex[:6]}@test.com"
        token = await _registrar_estudiante(client, email)
        assert isinstance(token, str) and len(token) > 0

    async def test_login_password_incorrecta(self, client: AsyncClient):
        email = f"pw_{uuid4().hex[:6]}@test.com"
        await _registrar_estudiante(client, email)
        r = await client.post("/api/v1/auth/login", json={"email": email, "password": "wrong"})
        assert r.status_code == 401

    async def test_logout_blacklist(self, client: AsyncClient):
        email = f"logout_{uuid4().hex[:6]}@test.com"
        token = await _registrar_estudiante(client, email)
        h = {"Authorization": f"Bearer {token}"}
        r = await client.post("/api/v1/auth/logout", headers=h)
        assert r.status_code == 204
        r2 = await client.get("/api/v1/auth/me", headers=h)
        assert r2.status_code == 401

    async def test_sin_token_rechazado(self, client: AsyncClient):
        r = await client.get("/api/v1/solicitudes/")
        assert r.status_code in (401, 403)

    async def test_token_invalido_rechazado(self, client: AsyncClient):
        r = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer falso_xyz"})
        assert r.status_code == 401

    async def test_actualizar_perfil(self, client: AsyncClient):
        email = f"upd_{uuid4().hex[:6]}@test.com"
        token = await _registrar_estudiante(client, email)
        r = await client.patch("/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"nombre": "Actualizado"})
        assert r.status_code == 200
        assert r.json()["nombre"] == "Actualizado"


# ──────────────────────────────────────────────────────────────────────────────
# Control de acceso por rol
# ──────────────────────────────────────────────────────────────────────────────

class TestControlAcceso:

    async def test_estudiante_no_puede_revisar(self, client: AsyncClient):
        token_e = await _registrar_estudiante(client, f"e_{uuid4().hex[:6]}@test.com")
        sol_id = await _crear_solicitud(client, token_e)
        r = await client.patch(f"/api/v1/solicitudes/{sol_id}/revisar",
            headers={"Authorization": f"Bearer {token_e}", "Content-Type": "application/json"},
            json={})
        assert r.status_code == 403

    async def test_estudiante_no_puede_aprobar(self, client: AsyncClient):
        token_e = await _registrar_estudiante(client, f"e_{uuid4().hex[:6]}@test.com")
        sol_id = await _crear_solicitud(client, token_e)
        r = await client.patch(f"/api/v1/solicitudes/{sol_id}/aprobar",
            headers={"Authorization": f"Bearer {token_e}", "Content-Type": "application/json"},
            json={})
        assert r.status_code == 403

    async def test_coordinador_no_puede_aprobar(self, client: AsyncClient):
        token_r = await _login_rector(client)
        token_c = await _crear_coordinador_y_login(client, token_r, f"c_{uuid4().hex[:6]}@test.com")
        token_e = await _registrar_estudiante(client, f"e_{uuid4().hex[:6]}@test.com")
        sol_id = await _crear_solicitud(client, token_e)
        r = await client.patch(f"/api/v1/solicitudes/{sol_id}/aprobar",
            headers={"Authorization": f"Bearer {token_c}", "Content-Type": "application/json"},
            json={})
        assert r.status_code == 403

    async def test_estudiante_no_ve_solicitud_ajena(self, client: AsyncClient):
        token_e1 = await _registrar_estudiante(client, f"e1_{uuid4().hex[:6]}@test.com")
        token_e2 = await _registrar_estudiante(client, f"e2_{uuid4().hex[:6]}@test.com")
        sol_id = await _crear_solicitud(client, token_e1)
        r = await client.get(f"/api/v1/solicitudes/{sol_id}",
            headers={"Authorization": f"Bearer {token_e2}"})
        assert r.status_code == 403

    async def test_estudiante_no_puede_crear_usuarios(self, client: AsyncClient):
        token_e = await _registrar_estudiante(client, f"e_{uuid4().hex[:6]}@test.com")
        r = await client.post("/api/v1/usuarios/",
            headers={"Authorization": f"Bearer {token_e}", "Content-Type": "application/json"},
            json={"nombre": "X", "apellido": "Y", "email": f"x_{uuid4().hex[:6]}@test.com",
                  "password": "123456", "rol": "estudiante"})
        assert r.status_code == 403

    async def test_coordinador_no_puede_subir_notas(self, client: AsyncClient):
        token_r = await _login_rector(client)
        token_c = await _crear_coordinador_y_login(client, token_r, f"c_{uuid4().hex[:6]}@test.com")
        token_e = await _registrar_estudiante(client, f"e_{uuid4().hex[:6]}@test.com")
        sol_id = await _crear_solicitud(client, token_e)
        r = await client.post(f"/api/v1/documentos/{sol_id}/notas",
            headers={"Authorization": f"Bearer {token_c}"},
            files={"file": ("f.pdf", fake_pdf(), "application/pdf")})
        assert r.status_code == 403

    async def test_estudiante_no_puede_subir_pensum_destino(self, client: AsyncClient):
        token_e = await _registrar_estudiante(client, f"e_{uuid4().hex[:6]}@test.com")
        sol_id = await _crear_solicitud(client, token_e)
        r = await client.post(f"/api/v1/documentos/{sol_id}/pensum-destino",
            headers={"Authorization": f"Bearer {token_e}"},
            files={"file": ("f.pdf", fake_pdf(), "application/pdf")})
        assert r.status_code == 403


# ──────────────────────────────────────────────────────────────────────────────
# Solicitudes
# ──────────────────────────────────────────────────────────────────────────────

class TestSolicitudes:

    async def test_crear_solicitud_con_datos_contacto(self, client: AsyncClient):
        token = await _registrar_estudiante(client, f"e_{uuid4().hex[:6]}@test.com")
        r = await client.post("/api/v1/solicitudes/",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "cedula": "1061529242", "telefono": "3148757616",
                "correo_contacto": "test@test.com",
                "institucion_origen": "SENA", "programa_origen": "ADSI",
                "institucion_destino": "Uniautónoma", "programa_destino": "Ing. Software"
            })
        assert r.status_code == 201
        data = r.json()
        assert data["estado"] == "borrador"
        assert data["cedula"] == "1061529242"
        assert data["telefono"] == "3148757616"

    async def test_enviar_sin_notas_falla(self, client: AsyncClient):
        token = await _registrar_estudiante(client, f"e_{uuid4().hex[:6]}@test.com")
        sol_id = await _crear_solicitud(client, token)
        r = await client.patch(f"/api/v1/solicitudes/{sol_id}/enviar",
            headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 400
        assert "notas" in r.json()["detail"].lower()

    async def test_enviar_con_notas_ok(self, client: AsyncClient):
        token = await _registrar_estudiante(client, f"e_{uuid4().hex[:6]}@test.com")
        sol_id = await _crear_solicitud(client, token)
        await _subir_notas(client, token, sol_id)
        r = await client.patch(f"/api/v1/solicitudes/{sol_id}/enviar",
            headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["estado"] == "enviada"

    async def test_enviar_doble_falla(self, client: AsyncClient):
        token = await _registrar_estudiante(client, f"e_{uuid4().hex[:6]}@test.com")
        sol_id = await _crear_solicitud(client, token)
        await _subir_notas(client, token, sol_id)
        await client.patch(f"/api/v1/solicitudes/{sol_id}/enviar",
            headers={"Authorization": f"Bearer {token}"})
        r = await client.patch(f"/api/v1/solicitudes/{sol_id}/enviar",
            headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 400

    async def test_paginacion_estructura(self, client: AsyncClient):
        token_r = await _login_rector(client)
        r = await client.get("/api/v1/solicitudes/?page=1&size=5",
            headers={"Authorization": f"Bearer {token_r}"})
        assert r.status_code == 200
        body = r.json()
        assert "total" in body
        assert "page" in body
        assert "size" in body
        assert "items" in body
        assert isinstance(body["items"], list)
        assert len(body["items"]) <= 5

    async def test_filtro_por_estado(self, client: AsyncClient):
        token_r = await _login_rector(client)
        r = await client.get("/api/v1/solicitudes/?estado=borrador",
            headers={"Authorization": f"Bearer {token_r}"})
        assert r.status_code == 200
        for item in r.json()["items"]:
            assert item["estado"] == "borrador"

    async def test_historial_estados(self, client: AsyncClient):
        token = await _registrar_estudiante(client, f"e_{uuid4().hex[:6]}@test.com")
        sol_id = await _crear_solicitud(client, token)
        await _subir_notas(client, token, sol_id)
        await client.patch(f"/api/v1/solicitudes/{sol_id}/enviar",
            headers={"Authorization": f"Bearer {token}"})
        r = await client.get(f"/api/v1/solicitudes/{sol_id}/historial",
            headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert len(r.json()) >= 1


# ──────────────────────────────────────────────────────────────────────────────
# Documentos
# ──────────────────────────────────────────────────────────────────────────────

class TestDocumentos:

    async def test_subir_notas_ok(self, client: AsyncClient):
        token = await _registrar_estudiante(client, f"e_{uuid4().hex[:6]}@test.com")
        sol_id = await _crear_solicitud(client, token)
        r = await client.post(f"/api/v1/documentos/{sol_id}/notas",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("notas.pdf", fake_pdf(), "application/pdf")})
        assert r.status_code == 201
        assert r.json()["tipo"] == "pensum_origen"

    async def test_subir_notas_no_pdf_falla(self, client: AsyncClient):
        token = await _registrar_estudiante(client, f"e_{uuid4().hex[:6]}@test.com")
        sol_id = await _crear_solicitud(client, token)
        r = await client.post(f"/api/v1/documentos/{sol_id}/notas",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("img.jpg", b"fake image", "image/jpeg")})
        assert r.status_code == 400

    async def test_resubir_notas_actualiza(self, client: AsyncClient):
        token = await _registrar_estudiante(client, f"e_{uuid4().hex[:6]}@test.com")
        sol_id = await _crear_solicitud(client, token)
        r1 = await client.post(f"/api/v1/documentos/{sol_id}/notas",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("notas.pdf", fake_pdf(), "application/pdf")})
        r2 = await client.post(f"/api/v1/documentos/{sol_id}/notas",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("notas_v2.pdf", fake_pdf(), "application/pdf")})
        assert r2.status_code == 201
        # Mismo ID — upsert, no duplicado
        assert r1.json()["id"] == r2.json()["id"]

    async def test_pensum_destino_solo_en_revision(self, client: AsyncClient):
        token_r = await _login_rector(client)
        token_c = await _crear_coordinador_y_login(client, token_r, f"c_{uuid4().hex[:6]}@test.com")
        token_e = await _registrar_estudiante(client, f"e_{uuid4().hex[:6]}@test.com")
        sol_id = await _crear_solicitud(client, token_e)

        # En BORRADOR debe fallar
        r = await client.post(f"/api/v1/documentos/{sol_id}/pensum-destino",
            headers={"Authorization": f"Bearer {token_c}"},
            files={"file": ("pensum.pdf", fake_pdf(), "application/pdf")})
        assert r.status_code == 400

    async def test_pensum_destino_ok_en_revision(self, client: AsyncClient):
        token_r = await _login_rector(client)
        token_c = await _crear_coordinador_y_login(client, token_r, f"c_{uuid4().hex[:6]}@test.com")
        token_e = await _registrar_estudiante(client, f"e_{uuid4().hex[:6]}@test.com")
        sol_id = await _crear_solicitud(client, token_e)
        await _subir_notas(client, token_e, sol_id)
        await client.patch(f"/api/v1/solicitudes/{sol_id}/enviar",
            headers={"Authorization": f"Bearer {token_e}"})
        await client.patch(f"/api/v1/solicitudes/{sol_id}/revisar",
            headers={"Authorization": f"Bearer {token_c}", "Content-Type": "application/json"},
            json={})
        r = await client.post(f"/api/v1/documentos/{sol_id}/pensum-destino",
            headers={"Authorization": f"Bearer {token_c}"},
            files={"file": ("pensum.pdf", fake_pdf(), "application/pdf")})
        assert r.status_code == 201
        assert r.json()["tipo"] == "pensum_destino"

    async def test_listar_documentos(self, client: AsyncClient):
        token = await _registrar_estudiante(client, f"e_{uuid4().hex[:6]}@test.com")
        sol_id = await _crear_solicitud(client, token)
        await _subir_notas(client, token, sol_id)
        r = await client.get(f"/api/v1/documentos/{sol_id}",
            headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert len(r.json()) == 1  # Solo notas por ahora


# ──────────────────────────────────────────────────────────────────────────────
# Usuarios CRUD
# ──────────────────────────────────────────────────────────────────────────────

class TestUsuarios:

    async def test_rector_crea_coordinador(self, client: AsyncClient):
        token_r = await _login_rector(client)
        email = f"coord_{uuid4().hex[:6]}@test.com"
        r = await client.post("/api/v1/usuarios/",
            headers={"Authorization": f"Bearer {token_r}", "Content-Type": "application/json"},
            json={"nombre": "Ana", "apellido": "Coord", "email": email,
                  "password": "Coord2024!", "rol": "coordinador"})
        assert r.status_code == 201
        assert r.json()["rol"] == "coordinador"

    async def test_rector_lista_con_paginacion(self, client: AsyncClient):
        token_r = await _login_rector(client)
        r = await client.get("/api/v1/usuarios/?page=1&size=10",
            headers={"Authorization": f"Bearer {token_r}"})
        assert r.status_code == 200
        body = r.json()
        assert "total" in body and "items" in body

    async def test_rector_desactiva_y_reactiva(self, client: AsyncClient):
        token_r = await _login_rector(client)
        email = f"d_{uuid4().hex[:6]}@test.com"
        r = await client.post("/api/v1/usuarios/",
            headers={"Authorization": f"Bearer {token_r}", "Content-Type": "application/json"},
            json={"nombre": "X", "apellido": "Y", "email": email,
                  "password": "Test2024!", "rol": "estudiante"})
        uid = r.json()["id"]

        des = await client.patch(f"/api/v1/usuarios/{uid}/desactivar",
            headers={"Authorization": f"Bearer {token_r}"})
        assert des.status_code == 200
        assert des.json()["activo"] is False

        # Login debe fallar
        login = await client.post("/api/v1/auth/login",
            json={"email": email, "password": "Test2024!"})
        assert login.status_code == 403

        act = await client.patch(f"/api/v1/usuarios/{uid}/activar",
            headers={"Authorization": f"Bearer {token_r}"})
        assert act.status_code == 200
        assert act.json()["activo"] is True

    async def test_rector_no_se_desactiva_a_si_mismo(self, client: AsyncClient):
        token_r = await _login_rector(client)
        me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_r}"})
        uid = me.json()["id"]
        r = await client.patch(f"/api/v1/usuarios/{uid}/desactivar",
            headers={"Authorization": f"Bearer {token_r}"})
        assert r.status_code == 400

    async def test_filtro_rol_usuarios(self, client: AsyncClient):
        token_r = await _login_rector(client)
        r = await client.get("/api/v1/usuarios/?rol=estudiante",
            headers={"Authorization": f"Bearer {token_r}"})
        assert r.status_code == 200
        for u in r.json()["items"]:
            assert u["rol"] == "estudiante"


# ──────────────────────────────────────────────────────────────────────────────
# Email service (unit tests con mock)
# ──────────────────────────────────────────────────────────────────────────────

class TestEmailService:

    @patch("app.services.email_service.settings")
    async def test_no_falla_sin_smtp(self, mock_settings):
        mock_settings.SMTP_HOST = None
        mock_settings.SMTP_USER = None
        mock_settings.SMTP_PASSWORD = None
        mock_settings.EMAIL_FROM = None
        from app.services.email_service import notificar_cambio_estado
        # No debe lanzar excepción
        await notificar_cambio_estado(
            email_estudiante="test@test.com",
            nombre_estudiante="Test",
            solicitud_id=str(uuid4()),
            estado_anterior="borrador",
            estado_nuevo="enviada",
        )

    @patch("app.services.email_service._email_configurado", return_value=True)
    @patch("app.services.email_service.aiosmtplib")
    async def test_envia_con_smtp_configurado(self, mock_smtp, mock_configurado):
        mock_smtp.send = AsyncMock()
        from app.services.email_service import notificar_cambio_estado
        await notificar_cambio_estado(
            email_estudiante="estudiante@test.com",
            nombre_estudiante="Carlos",
            solicitud_id=str(uuid4()),
            estado_anterior="borrador",
            estado_nuevo="enviada",
        )
        mock_smtp.send.assert_called_once()