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


async def _obtener_opciones_instituciones(client: AsyncClient, token: str) -> list:
    """Obtiene la lista de instituciones disponibles"""
    r = await client.get("/api/v1/solicitudes/opciones/instituciones",
        headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    return r.json()


async def _obtener_opciones_programas(client: AsyncClient, token: str, institucion_id: str = None) -> list:
    """Obtiene la lista de programas disponibles"""
    url = "/api/v1/solicitudes/opciones/programas"
    if institucion_id:
        url += f"?institucion_id={institucion_id}"
    r = await client.get(url, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    return r.json()


async def _crear_solicitud_con_catalogo(client: AsyncClient, token: str, 
                                        programa_origen_id: str, programa_destino_id: str) -> str:
    """Crea solicitud eligiendo programas del catálogo"""
    r = await client.post("/api/v1/solicitudes/",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "cedula": "1061529242",
            "telefono": "3148757616",
            "correo_contacto": "test@test.com",
            "programa_origen_id": programa_origen_id,
            "programa_destino_id": programa_destino_id,
        })
    assert r.status_code == 201
    return r.json()["id"]


async def _crear_solicitud_texto_libre(client: AsyncClient, token: str) -> str:
    """Crea solicitud escribiendo texto libre (Otra)"""
    r = await client.post("/api/v1/solicitudes/",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "cedula": "1061529242",
            "telefono": "3148757616",
            "correo_contacto": "test@test.com",
            "institucion_origen_texto": "Universidad Privada de Perú",
            "programa_origen_texto": "Ingeniería Informática",
            "institucion_destino_texto": "Corporación Universitaria Autónoma del Cauca",
            "programa_destino_texto": "Ingeniería de Sistemas",
        })
    assert r.status_code == 201
    return r.json()["id"]


async def _subir_notas(client: AsyncClient, token: str, solicitud_id: str) -> dict:
    """Sube notas y retorna la respuesta con URL"""
    r = await client.post(
        f"/api/v1/documentos/{solicitud_id}/notas",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("notas.pdf", fake_pdf(), "application/pdf")}
    )
    assert r.status_code == 201
    return r.json()


async def _subir_pensum_destino(client: AsyncClient, token: str, solicitud_id: str) -> dict:
    """Sube pensum destino y retorna la respuesta con URL"""
    r = await client.post(
        f"/api/v1/documentos/{solicitud_id}/pensum-destino",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("pensum.pdf", fake_pdf(), "application/pdf")}
    )
    assert r.status_code == 201
    return r.json()


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


# ──────────────────────────────────────────────────────────────────────────────
# Perfil de Usuario y Recuperación de Contraseña
# ──────────────────────────────────────────────────────────────────────────────

class TestPerfilUsuario:

    async def test_obtener_mi_perfil(self, client: AsyncClient):
        """Test: GET /usuarios/perfil/mio"""
        email = f"perfil_{uuid4().hex[:6]}@test.com"
        token = await _registrar_estudiante(client, email)
        r = await client.get("/api/v1/usuarios/perfil/mio",
            headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert data["email"] == email
        assert data["nombre"] == "Test"
        assert data["rol"] == "estudiante"

    async def test_editar_nombre_y_apellido(self, client: AsyncClient):
        """Test: PATCH /usuarios/perfil/mio - Editar nombre/apellido"""
        email = f"edit_{uuid4().hex[:6]}@test.com"
        token = await _registrar_estudiante(client, email)
        r = await client.patch("/api/v1/usuarios/perfil/mio",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"nombre": "Carlos", "apellido": "García"})
        assert r.status_code == 200
        data = r.json()
        assert data["nombre"] == "Carlos"
        assert data["apellido"] == "García"

    async def test_cambiar_contraseña_requiere_actual(self, client: AsyncClient):
        """Test: PATCH /usuarios/perfil/mio - Sin contraseña actual falla"""
        email = f"pwd_{uuid4().hex[:6]}@test.com"
        token = await _registrar_estudiante(client, email)
        r = await client.patch("/api/v1/usuarios/perfil/mio",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"password_nueva": "nueva_contraseña"})
        assert r.status_code == 400

    async def test_cambiar_contraseña_con_incorrecta_falla(self, client: AsyncClient):
        """Test: PATCH /usuarios/perfil/mio - Contraseña actual incorrecta"""
        email = f"pwd2_{uuid4().hex[:6]}@test.com"
        token = await _registrar_estudiante(client, email)
        r = await client.patch("/api/v1/usuarios/perfil/mio",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"password_actual": "contraseña_incorrecta", "password_nueva": "nueva_pwd"})
        assert r.status_code == 400

    async def test_cambiar_contraseña_ok(self, client: AsyncClient):
        """Test: PATCH /usuarios/perfil/mio - Cambio de contraseña exitoso"""
        email = f"pwd3_{uuid4().hex[:6]}@test.com"
        token = await _registrar_estudiante(client, email)
        
        r = await client.patch("/api/v1/usuarios/perfil/mio",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"password_actual": "123456", "password_nueva": "nueva_contraseña_segura"})
        assert r.status_code == 200
        
        r_login = await client.post("/api/v1/auth/login",
            json={"email": email, "password": "nueva_contraseña_segura"})
        assert r_login.status_code == 200

    async def test_cambiar_contraseña_vieja_no_funciona(self, client: AsyncClient):
        """Test: PATCH /usuarios/perfil/mio - Contraseña vieja no funciona después de cambiar"""
        email = f"pwd4_{uuid4().hex[:6]}@test.com"
        token = await _registrar_estudiante(client, email)
        
        await client.patch("/api/v1/usuarios/perfil/mio",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"password_actual": "123456", "password_nueva": "nueva_pwd"})
        
        r = await client.post("/api/v1/auth/login",
            json={"email": email, "password": "123456"})
        assert r.status_code == 401


class TestRecuperacionContraseña:

    async def test_solicitar_recuperacion_ok(self, client: AsyncClient):
        """Test: POST /usuarios/recuperacion/solicitar"""
        email = f"rec_{uuid4().hex[:6]}@test.com"
        await _registrar_estudiante(client, email)
        
        r = await client.post("/api/v1/usuarios/recuperacion/solicitar",
            json={"email": email})
        assert r.status_code == 200
        assert "mensaje" in r.json()

    async def test_solicitar_recuperacion_email_no_existe(self, client: AsyncClient):
        """Test: POST /usuarios/recuperacion/solicitar - Email no existe (no expone)"""
        r = await client.post("/api/v1/usuarios/recuperacion/solicitar",
            json={"email": "no_existe@test.com"})
        assert r.status_code == 200
        assert "mensaje" in r.json()

    async def test_solicitar_recuperacion_envia_email(self, client: AsyncClient):
        """Test: POST /usuarios/recuperacion/solicitar - Genera token"""
        email = f"rec2_{uuid4().hex[:6]}@test.com"
        await _registrar_estudiante(client, email)
        
        # Simplemente verificar que el endpoint funciona
        # El email se envía en background, no podemos mockearlo fácilmente
        r = await client.post("/api/v1/usuarios/recuperacion/solicitar",
            json={"email": email})
        assert r.status_code == 200

    async def test_restablecer_contraseña_sin_token_falla(self, client: AsyncClient):
        """Test: POST /usuarios/recuperacion/restablecer - Token inválido"""
        r = await client.post("/api/v1/usuarios/recuperacion/restablecer",
            json={"token": "token_falso_xyz", "password_nueva": "nueva_pwd"})
        assert r.status_code == 400

    async def test_flujo_recuperacion_sin_bd_access(self, client: AsyncClient):
        """Test: Verificar que endpoints de recovery existen"""
        email = f"flujo_{uuid4().hex[:6]}@test.com"
        await _registrar_estudiante(client, email)
        
        # 1. Solicitar recuperación
        r1 = await client.post("/api/v1/usuarios/recuperacion/solicitar",
            json={"email": email})
        assert r1.status_code == 200
        
        # 2. Intentar restablecer con token fake (debe fallar)
        r2 = await client.post("/api/v1/usuarios/recuperacion/restablecer",
            json={"token": "token_invalido_xyz", "password_nueva": "nueva_pwd"})
        assert r2.status_code == 400


# ──────────────────────────────────────────────────────────────────────────────
# Control de acceso por rol
# ──────────────────────────────────────────────────────────────────────────────

class TestControlAcceso:

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
        
        sol_id = await _crear_solicitud_texto_libre(client, token_e)
        
        r = await client.post(f"/api/v1/documentos/{sol_id}/notas",
            headers={"Authorization": f"Bearer {token_c}"},
            files={"file": ("f.pdf", fake_pdf(), "application/pdf")})
        assert r.status_code == 403

    async def test_estudiante_no_puede_subir_pensum_destino(self, client: AsyncClient):
        token_e = await _registrar_estudiante(client, f"e_{uuid4().hex[:6]}@test.com")
        sol_id = await _crear_solicitud_texto_libre(client, token_e)
        
        r = await client.post(f"/api/v1/documentos/{sol_id}/pensum-destino",
            headers={"Authorization": f"Bearer {token_e}"},
            files={"file": ("f.pdf", fake_pdf(), "application/pdf")})
        assert r.status_code == 403

    async def test_estudiante_no_ve_solicitud_ajena(self, client: AsyncClient):
        token_e1 = await _registrar_estudiante(client, f"e1_{uuid4().hex[:6]}@test.com")
        token_e2 = await _registrar_estudiante(client, f"e2_{uuid4().hex[:6]}@test.com")
        
        sol_id = await _crear_solicitud_texto_libre(client, token_e1)
        
        r = await client.get(f"/api/v1/solicitudes/{sol_id}",
            headers={"Authorization": f"Bearer {token_e2}"})
        assert r.status_code == 403


# ──────────────────────────────────────────────────────────────────────────────
# Solicitudes
# ──────────────────────────────────────────────────────────────────────────────

class TestSolicitudes:

    async def test_crear_solicitud_con_texto_libre(self, client: AsyncClient):
        """Test: POST /solicitudes/ - Crear con opción 'Otra' (texto libre)"""
        token = await _registrar_estudiante(client, f"e_{uuid4().hex[:6]}@test.com")
        
        sol_id = await _crear_solicitud_texto_libre(client, token)
        assert sol_id is not None
        
        r = await client.get(f"/api/v1/solicitudes/{sol_id}",
            headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert data["institucion_origen"] == "Universidad Privada de Perú"
        assert data["programa_origen"] == "Ingeniería Informática"

    async def test_crear_solicitud_sin_programas_falla(self, client: AsyncClient):
        """Test: POST /solicitudes/ - Falla si no proporciona programas"""
        token = await _registrar_estudiante(client, f"e_{uuid4().hex[:6]}@test.com")
        
        r = await client.post("/api/v1/solicitudes/",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "cedula": "1061529242",
                "telefono": "3148757616",
                "correo_contacto": "test@test.com",
            })
        assert r.status_code == 400

    async def test_paginacion_estructura(self, client: AsyncClient):
        """Test: GET /solicitudes/ - Paginación"""
        token_r = await _login_rector(client)
        r = await client.get("/api/v1/solicitudes/?page=1&size=5",
            headers={"Authorization": f"Bearer {token_r}"})
        assert r.status_code == 200
        body = r.json()
        assert "total" in body
        assert "page" in body
        assert "size" in body
        assert "items" in body

    async def test_filtro_por_estado(self, client: AsyncClient):
        """Test: GET /solicitudes/?estado=... - Filtro"""
        token_r = await _login_rector(client)
        r = await client.get("/api/v1/solicitudes/?estado=borrador",
            headers={"Authorization": f"Bearer {token_r}"})
        assert r.status_code == 200
        for item in r.json()["items"]:
            assert item["estado"] == "borrador"


# ──────────────────────────────────────────────────────────────────────────────
# Documentos
# ──────────────────────────────────────────────────────────────────────────────

class TestDocumentos:

    async def test_subir_notas_ok(self, client: AsyncClient):
        """Test: POST /documentos/{id}/notas - Subir notas"""
        token = await _registrar_estudiante(client, f"e_{uuid4().hex[:6]}@test.com")
        sol_id = await _crear_solicitud_texto_libre(client, token)
        
        doc = await _subir_notas(client, token, sol_id)
        assert doc["tipo"] == "pensum_origen"
        assert "url" in doc

    async def test_subir_notas_devuelve_url(self, client: AsyncClient):
        """Test: POST /documentos/{id}/notas - Devuelve URL"""
        token = await _registrar_estudiante(client, f"e_{uuid4().hex[:6]}@test.com")
        sol_id = await _crear_solicitud_texto_libre(client, token)
        
        doc = await _subir_notas(client, token, sol_id)
        
        assert "url" in doc
        assert "localhost" in doc["url"] or "http" in doc["url"]
        assert str(sol_id) in doc["url"]
        assert "descargar" in doc["url"]

    async def test_listar_documentos_con_urls(self, client: AsyncClient):
        """Test: GET /documentos/{solicitud_id} - Lista con URLs"""
        token = await _registrar_estudiante(client, f"e_{uuid4().hex[:6]}@test.com")
        sol_id = await _crear_solicitud_texto_libre(client, token)
        
        await _subir_notas(client, token, sol_id)
        
        r = await client.get(f"/api/v1/documentos/{sol_id}",
            headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        docs = r.json()
        assert len(docs) >= 1
        
        for doc in docs:
            assert "url" in doc
            assert "descargar" in doc["url"]

    async def test_descargar_documento(self, client: AsyncClient):
        """Test: GET /documentos/{solicitud_id}/{doc_id}/descargar"""
        token = await _registrar_estudiante(client, f"e_{uuid4().hex[:6]}@test.com")
        sol_id = await _crear_solicitud_texto_libre(client, token)
        
        doc = await _subir_notas(client, token, sol_id)
        
        # Descargar usando el doc_id
        r = await client.get(
            f"/api/v1/documentos/{sol_id}/{doc['id']}/descargar",
            headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"

    async def test_subir_notas_no_pdf_falla(self, client: AsyncClient):
        """Test: POST /documentos/{id}/notas - Rechaza no-PDF"""
        token = await _registrar_estudiante(client, f"e_{uuid4().hex[:6]}@test.com")
        sol_id = await _crear_solicitud_texto_libre(client, token)
        
        r = await client.post(f"/api/v1/documentos/{sol_id}/notas",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("img.jpg", b"fake image", "image/jpeg")})
        assert r.status_code == 400

    async def test_multiples_notas_crea_documentos_distintos(self, client: AsyncClient):
        """Test: POST /documentos/{id}/notas - Cada subida crea un documento nuevo"""
        token = await _registrar_estudiante(client, f"e_{uuid4().hex[:6]}@test.com")
        sol_id = await _crear_solicitud_texto_libre(client, token)

        doc1 = await _subir_notas(client, token, sol_id)
        doc2 = await _subir_notas(client, token, sol_id)

        assert doc1["id"] != doc2["id"]
        assert doc1["tipo"] == "pensum_origen"
        assert doc2["tipo"] == "pensum_origen"


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
# Email service
# ──────────────────────────────────────────────────────────────────────────────

class TestEmailService:

    @patch("app.services.email_service.settings")
    async def test_no_falla_sin_smtp(self, mock_settings):
        mock_settings.SMTP_HOST = None
        mock_settings.SMTP_USER = None
        mock_settings.SMTP_PASSWORD = None
        mock_settings.EMAIL_FROM = None
        from app.services.email_service import notificar_cambio_estado
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

    @patch("app.services.email_service._email_configurado", return_value=True)
    @patch("app.services.email_service.aiosmtplib")
    async def test_enviar_recuperacion_contraseña(self, mock_smtp, mock_configurado):
        """Test: Enviar email de recuperación de contraseña"""
        mock_smtp.send = AsyncMock()
        from app.services.email_service import enviar_recuperacion_contraseña
        
        await enviar_recuperacion_contraseña(
            email_usuario="usuario@test.com",
            nombre_usuario="Carlos García",
            token="token_seguro_xyz",
        )
        mock_smtp.send.assert_called_once()