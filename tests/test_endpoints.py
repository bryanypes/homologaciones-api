import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4
import io

def fake_pdf() -> bytes:
    return b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\nxref\n0 1\n0000000000 65535 f\ntrailer\n<< /Size 1 /Root 1 0 R >>\nstartxref\n9\n%%EOF"

async def _registrar_estudiante(client: AsyncClient, email: str) -> str:
    await client.post("/api/v1/auth/register", json={
        "nombre": "Test", "apellido": "User",
        "email": email, "password": "123456", "rol": "estudiante"
    })
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": "123456"})
    return r.json()["access_token"]

async def _login_rector(client: AsyncClient) -> str:
    r = await client.post("/api/v1/auth/login", json={
        "email": "vicerrector@universidad.edu.co", "password": "Rector2024!"
    })
    assert r.status_code == 200, "El seed del rector no corrió"
    return r.json()["access_token"]

async def _crear_coordinador_y_login(client: AsyncClient, token_rector: str, email: str) -> str:
    await client.post("/api/v1/usuarios/", headers={"Authorization": f"Bearer {token_rector}"},
        json={"nombre": "Coord", "apellido": "Test", "email": email, "password": "Coord2024!", "rol": "coordinador"})
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": "Coord2024!"})
    return r.json()["access_token"]

async def _obtener_opciones_instituciones(client: AsyncClient, token: str) -> list:
    r = await client.get("/api/v1/solicitudes/opciones/instituciones",
        headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    return r.json()

async def _obtener_opciones_programas(client: AsyncClient, token: str, institucion_id: str = None) -> list:
    url = "/api/v1/solicitudes/opciones/programas"
    if institucion_id:
        url += f"?institucion_id={institucion_id}"
    r = await client.get(url, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    return r.json()

async def _crear_solicitud_con_catalogo(client: AsyncClient, token: str,
                                        programa_origen_id: str, programa_destino_id: str) -> str:
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
    r = await client.post(
        f"/api/v1/documentos/{solicitud_id}/notas",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("notas.pdf", fake_pdf(), "application/pdf")}
    )
    assert r.status_code == 201
    return r.json()

async def _subir_pensum_destino(client: AsyncClient, token: str, solicitud_id: str) -> dict:
    r = await client.post(
        f"/api/v1/documentos/{solicitud_id}/pensum-destino",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("pensum.pdf", fake_pdf(), "application/pdf")}
    )
    assert r.status_code == 201
    return r.json()

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

    async def test_register_vicerrector_bloqueado(self, client: AsyncClient):
        r = await client.post("/api/v1/auth/register", json={
            "nombre": "X", "apellido": "Y", "email": f"r_{uuid4().hex[:6]}@test.com",
            "password": "123456", "rol": "vicerrector"
        })
        assert r.status_code == 400

    async def test_register_admin_bloqueado(self, client: AsyncClient):
        r = await client.post("/api/v1/auth/register", json={
            "nombre": "X", "apellido": "Y", "email": f"a_{uuid4().hex[:6]}@test.com",
            "password": "123456", "rol": "admin"
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

class TestPerfilUsuario:

    async def test_obtener_mi_perfil(self, client: AsyncClient):
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
        email = f"pwd_{uuid4().hex[:6]}@test.com"
        token = await _registrar_estudiante(client, email)
        r = await client.patch("/api/v1/usuarios/perfil/mio",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"password_nueva": "nueva_contraseña"})
        assert r.status_code == 400

    async def test_cambiar_contraseña_con_incorrecta_falla(self, client: AsyncClient):
        email = f"pwd2_{uuid4().hex[:6]}@test.com"
        token = await _registrar_estudiante(client, email)
        r = await client.patch("/api/v1/usuarios/perfil/mio",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"password_actual": "contraseña_incorrecta", "password_nueva": "nueva_pwd"})
        assert r.status_code == 400

    async def test_cambiar_contraseña_ok(self, client: AsyncClient):
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
        email = f"rec_{uuid4().hex[:6]}@test.com"
        await _registrar_estudiante(client, email)
        
        r = await client.post("/api/v1/usuarios/recuperacion/solicitar",
            json={"email": email})
        assert r.status_code == 200
        assert "mensaje" in r.json()

    async def test_solicitar_recuperacion_email_no_existe(self, client: AsyncClient):
        r = await client.post("/api/v1/usuarios/recuperacion/solicitar",
            json={"email": "no_existe@test.com"})
        assert r.status_code == 200
        assert "mensaje" in r.json()

    async def test_solicitar_recuperacion_envia_email(self, client: AsyncClient):
        email = f"rec2_{uuid4().hex[:6]}@test.com"
        await _registrar_estudiante(client, email)
        
        r = await client.post("/api/v1/usuarios/recuperacion/solicitar",
            json={"email": email})
        assert r.status_code == 200

    async def test_restablecer_contraseña_sin_token_falla(self, client: AsyncClient):
        r = await client.post("/api/v1/usuarios/recuperacion/restablecer",
            json={"token": "token_falso_xyz", "password_nueva": "nueva_pwd"})
        assert r.status_code == 400

    async def test_flujo_recuperacion_sin_bd_access(self, client: AsyncClient):
        email = f"flujo_{uuid4().hex[:6]}@test.com"
        await _registrar_estudiante(client, email)
        
        r1 = await client.post("/api/v1/usuarios/recuperacion/solicitar",
            json={"email": email})
        assert r1.status_code == 200
        
        r2 = await client.post("/api/v1/usuarios/recuperacion/restablecer",
            json={"token": "token_invalido_xyz", "password_nueva": "nueva_pwd"})
        assert r2.status_code == 400

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

class TestSolicitudes:

    async def test_crear_solicitud_con_texto_libre(self, client: AsyncClient):
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
        token_r = await _login_rector(client)
        r = await client.get("/api/v1/solicitudes/?estado=borrador",
            headers={"Authorization": f"Bearer {token_r}"})
        assert r.status_code == 200
        for item in r.json()["items"]:
            assert item["estado"] == "borrador"

class TestDocumentos:

    async def test_subir_notas_ok(self, client: AsyncClient):
        token = await _registrar_estudiante(client, f"e_{uuid4().hex[:6]}@test.com")
        sol_id = await _crear_solicitud_texto_libre(client, token)
        
        doc = await _subir_notas(client, token, sol_id)
        assert doc["tipo"] == "pensum_origen"
        assert "url" in doc

    async def test_subir_notas_devuelve_url(self, client: AsyncClient):
        token = await _registrar_estudiante(client, f"e_{uuid4().hex[:6]}@test.com")
        sol_id = await _crear_solicitud_texto_libre(client, token)
        
        doc = await _subir_notas(client, token, sol_id)
        
        assert "url" in doc
        assert "localhost" in doc["url"] or "http" in doc["url"]
        assert str(sol_id) in doc["url"]
        assert "descargar" in doc["url"]

    async def test_listar_documentos_con_urls(self, client: AsyncClient):
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
        token = await _registrar_estudiante(client, f"e_{uuid4().hex[:6]}@test.com")
        sol_id = await _crear_solicitud_texto_libre(client, token)
        
        doc = await _subir_notas(client, token, sol_id)
        
        r = await client.get(
            f"/api/v1/documentos/{sol_id}/{doc['id']}/descargar",
            headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"

    async def test_subir_notas_no_pdf_falla(self, client: AsyncClient):
        token = await _registrar_estudiante(client, f"e_{uuid4().hex[:6]}@test.com")
        sol_id = await _crear_solicitud_texto_libre(client, token)
        
        r = await client.post(f"/api/v1/documentos/{sol_id}/notas",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("img.jpg", b"fake image", "image/jpeg")})
        assert r.status_code == 400

    async def test_multiples_notas_crea_documentos_distintos(self, client: AsyncClient):
        token = await _registrar_estudiante(client, f"e_{uuid4().hex[:6]}@test.com")
        sol_id = await _crear_solicitud_texto_libre(client, token)

        doc1 = await _subir_notas(client, token, sol_id)
        doc2 = await _subir_notas(client, token, sol_id)

        assert doc1["id"] != doc2["id"]
        assert doc1["tipo"] == "pensum_origen"
        assert doc2["tipo"] == "pensum_origen"

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

class TestEmailService:

    @patch("app.services.email_service.settings")
    async def test_no_falla_sin_api_key(self, mock_settings):
        mock_settings.BREVO_API_KEY = None
        from app.services.email_service import notificar_cambio_estado
        await notificar_cambio_estado(
            email_estudiante="test@test.com",
            nombre_estudiante="Test",
            solicitud_id=str(uuid4()),
            estado_anterior="borrador",
            estado_nuevo="enviada",
        )

    @patch("app.services.email_service.httpx")
    @patch("app.services.email_service.settings")
    async def test_envia_con_brevo_configurado(self, mock_settings, mock_httpx):
        mock_settings.BREVO_API_KEY = "xkeysib-test"
        mock_settings.EMAIL_FROM = "test@test.com"
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=MagicMock(raise_for_status=MagicMock()))
        mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_httpx.AsyncClient.return_value.__aexit__ = AsyncMock(return_value=False)
        from app.services.email_service import notificar_cambio_estado
        await notificar_cambio_estado(
            email_estudiante="estudiante@test.com",
            nombre_estudiante="Carlos",
            solicitud_id=str(uuid4()),
            estado_anterior="borrador",
            estado_nuevo="enviada",
        )
        mock_client.post.assert_called_once()

    @patch("app.services.email_service.httpx")
    @patch("app.services.email_service.settings")
    async def test_enviar_recuperacion_contraseña(self, mock_settings, mock_httpx):
        mock_settings.BREVO_API_KEY = "xkeysib-test"
        mock_settings.EMAIL_FROM = "test@test.com"
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=MagicMock(raise_for_status=MagicMock()))
        mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_httpx.AsyncClient.return_value.__aexit__ = AsyncMock(return_value=False)
        from app.services.email_service import enviar_recuperacion_contraseña
        await enviar_recuperacion_contraseña(
            email_usuario="usuario@test.com",
            nombre_usuario="Carlos García",
            token="token_seguro_xyz",
        )
        mock_client.post.assert_called_once()