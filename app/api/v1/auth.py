from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token
from app.core.deps import get_current_user
from app.models.usuario import Usuario, Rol
from app.schemas.usuario import UsuarioCreate, UsuarioResponse, LoginRequest, TokenResponse, UsuarioUpdate
import redis.asyncio as aioredis
from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["Autenticación"])


@router.post(
    "/register",
    response_model=UsuarioResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar estudiante",
    description=(
        "Registro público. Solo crea usuarios con rol **estudiante**. "
        "Para crear coordinadores o vicerrectores, el vicerrector debe usar `POST /usuarios/`."
    ),
    responses={
        201: {"description": "Usuario creado exitosamente"},
        400: {"description": "Email ya registrado o rol no permitido en registro público"},
    },
)
async def register(data: UsuarioCreate, db: AsyncSession = Depends(get_db)):
    # Registro público solo para estudiantes
    if data.rol != Rol.ESTUDIANTE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El registro público solo permite el rol 'estudiante'. "
                   "Para otros roles, contacte al administrador del sistema.",
        )

    result = await db.execute(select(Usuario).where(Usuario.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email ya registrado")

    usuario = Usuario(
        nombre=data.nombre,
        apellido=data.apellido,
        email=data.email,
        password_hash=hash_password(data.password),
        rol=Rol.ESTUDIANTE,
    )
    db.add(usuario)
    await db.commit()
    await db.refresh(usuario)
    return usuario


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Iniciar sesión",
    description="Autentica al usuario y retorna un token JWT.",
    responses={
        200: {"description": "Login exitoso, retorna JWT"},
        401: {"description": "Credenciales inválidas"},
        403: {"description": "Usuario inactivo"},
    },
)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Usuario).where(Usuario.email == data.email))
    usuario = result.scalar_one_or_none()

    if not usuario or not verify_password(data.password, usuario.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    if not usuario.activo:
        raise HTTPException(status_code=403, detail="Usuario inactivo")

    token = create_access_token({"sub": str(usuario.id), "rol": usuario.rol})
    return TokenResponse(access_token=token, usuario=usuario)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cerrar sesión",
    description="Invalida el token JWT actual agregándolo a una blacklist en Redis.",
)
async def logout(
    usuario: Usuario = Depends(get_current_user),
    credentials=Depends(__import__("fastapi").security.HTTPBearer()),
):
    r = aioredis.from_url(settings.REDIS_URL)
    token = credentials.credentials
    await r.setex(f"blacklist:{token}", settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60, "1")
    await r.aclose()


@router.get(
    "/me",
    response_model=UsuarioResponse,
    summary="Perfil del usuario",
    description="Retorna los datos del usuario autenticado.",
)
async def me(usuario: Usuario = Depends(get_current_user)):
    return usuario


@router.patch(
    "/me",
    response_model=UsuarioResponse,
    summary="Actualizar perfil",
    description="Permite al usuario actualizar su nombre, apellido o contraseña.",
)
async def actualizar_perfil(
    data: UsuarioUpdate,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    if data.nombre is not None:
        usuario.nombre = data.nombre
    if data.apellido is not None:
        usuario.apellido = data.apellido
    if data.password is not None:
        usuario.password_hash = hash_password(data.password)

    await db.commit()
    await db.refresh(usuario)
    return usuario