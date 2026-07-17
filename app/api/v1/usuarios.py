from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from uuid import UUID
from typing import Optional

from app.core.database import get_db
from app.core.deps import require_rol, get_current_user
from app.core.security import hash_password, verify_password, crear_reset_token_con_expiracion, verificar_reset_token_vigente
from app.models.usuario import Usuario, Rol
from app.schemas.usuario import (
    UsuarioResponse, 
    UsuarioCreate, 
    UsuarioUpdate,
    UsuarioEditarPerfil,
    SolicitarRecuperacionRequest,
    RestablecerContraseñaRequest,
    RecuperacionResponse
)
from app.schemas.paginacion import PaginatedResponse
from app.services.email_service import enviar_recuperacion_contraseña

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])


@router.get(
    "/",
    response_model=PaginatedResponse[UsuarioResponse],
    summary="Listar usuarios",
    description="El administrador puede listar y filtrar todos los usuarios.",
)
async def listar_usuarios(
    rol: Optional[Rol] = Query(None, description="Filtrar por rol"),
    activo: Optional[bool] = Query(None, description="Filtrar por estado activo/inactivo"),
    page: int = Query(1, ge=1, description="Número de página"),
    size: int = Query(20, ge=1, le=100, description="Resultados por página"),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol(Rol.ADMIN)),
):
    query = select(Usuario)
    count_query = select(func.count(Usuario.id))

    if rol is not None:
        query = query.where(Usuario.rol == rol)
        count_query = count_query.where(Usuario.rol == rol)
    if activo is not None:
        query = query.where(Usuario.activo == activo)
        count_query = count_query.where(Usuario.activo == activo)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    offset = (page - 1) * size
    query = query.order_by(Usuario.creado_en.desc()).offset(offset).limit(size)
    result = await db.execute(query)
    items = result.scalars().all()

    return PaginatedResponse(total=total, page=page, size=size, items=items)


@router.get(
    "/perfil/mio",
    response_model=UsuarioResponse,
    summary="Obtener mi perfil",
    description="Retorna los datos del usuario autenticado.",
)
async def obtener_mi_perfil(
    usuario: Usuario = Depends(get_current_user),
):
    return usuario


@router.get(
    "/{usuario_id}",
    response_model=UsuarioResponse,
    summary="Obtener usuario",
    description="Retorna el detalle de un usuario por ID.",
    responses={404: {"description": "Usuario no encontrado"}},
)
async def obtener_usuario(
    usuario_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_rol(Rol.ADMIN)),
):
    result = await db.execute(select(Usuario).where(Usuario.id == usuario_id))
    usuario = result.scalar_one_or_none()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return usuario


@router.post(
    "/",
    response_model=UsuarioResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear usuario (admin)",
    description=(
        "Solo el administrador puede crear usuarios con cualquier rol. "
        "El registro público solo permite estudiantes."
    ),
    responses={
        201: {"description": "Usuario creado"},
        400: {"description": "Email ya registrado"},
        403: {"description": "Solo el administrador puede crear usuarios"},
    },
)
async def crear_usuario(
    data: UsuarioCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_rol(Rol.ADMIN)),
):
    result = await db.execute(select(Usuario).where(Usuario.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email ya registrado")

    usuario = Usuario(
        nombre=data.nombre,
        apellido=data.apellido,
        email=data.email,
        password_hash=hash_password(data.password),
        rol=data.rol,
    )
    db.add(usuario)
    await db.commit()
    await db.refresh(usuario)
    return usuario


@router.patch(
    "/perfil/mio",
    response_model=UsuarioResponse,
    summary="Editar mi perfil",
    description=(
        "Permite al usuario autenticado editar su nombre, apellido o cambiar su contraseña. "
        "Si cambias la contraseña, debe proporcionar la contraseña actual."
    ),
    responses={
        400: {"description": "Contraseña actual incorrecta"},
        403: {"description": "No autenticado"},
    },
)
async def editar_mi_perfil(
    data: UsuarioEditarPerfil,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    """El usuario edita su propio perfil"""
    
    # Si cambia contraseña, verificar que proporcione la actual
    if data.password_nueva:
        if not data.password_actual:
            raise HTTPException(
                status_code=400,
                detail="Debes proporcionar tu contraseña actual para cambiarla"
            )
        
        if not verify_password(data.password_actual, usuario.password_hash):
            raise HTTPException(
                status_code=400,
                detail="Contraseña actual incorrecta"
            )
        
        usuario.password_hash = hash_password(data.password_nueva)
    
    if data.nombre is not None:
        usuario.nombre = data.nombre
    if data.apellido is not None:
        usuario.apellido = data.apellido

    await db.commit()
    await db.refresh(usuario)
    return usuario


@router.patch(
    "/{usuario_id}",
    response_model=UsuarioResponse,
    summary="Actualizar usuario (admin)",
    description="El administrador puede actualizar nombre, apellido, rol o contraseña de cualquier usuario.",
    responses={
        404: {"description": "Usuario no encontrado"},
        403: {"description": "Solo el administrador puede modificar usuarios"},
    },
)
async def actualizar_usuario(
    usuario_id: UUID,
    data: UsuarioUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_rol(Rol.ADMIN)),
):
    result = await db.execute(select(Usuario).where(Usuario.id == usuario_id))
    usuario = result.scalar_one_or_none()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if data.nombre is not None:
        usuario.nombre = data.nombre
    if data.apellido is not None:
        usuario.apellido = data.apellido
    if data.password is not None:
        usuario.password_hash = hash_password(data.password)
    if data.rol is not None:
        usuario.rol = data.rol
    if data.activo is not None:
        usuario.activo = data.activo

    await db.commit()
    await db.refresh(usuario)
    return usuario


@router.post(
    "/recuperacion/solicitar",
    response_model=RecuperacionResponse,
    summary="Solicitar recuperación de contraseña",
    description=(
        "Envía un token de recuperación al correo del usuario. "
        "El token es válido por 30 minutos."
    ),
    responses={
        404: {"description": "Usuario no encontrado"},
        200: {"description": "Correo de recuperación enviado"},
    },
)
async def solicitar_recuperacion(
    data: SolicitarRecuperacionRequest,
    db: AsyncSession = Depends(get_db),
):
    """Envía token de recuperación de contraseña al email"""
    
    result = await db.execute(select(Usuario).where(Usuario.email == data.email))
    usuario = result.scalar_one_or_none()
    
    if not usuario:
        # Por seguridad, no revelar si el email existe o no
        # Pero sí enviar la respuesta exitosa
        return RecuperacionResponse(
            mensaje="Si el correo está registrado, recibirás un enlace de recuperación"
        )
    
    # Generar token de reset
    token, expira = crear_reset_token_con_expiracion()
    usuario.reset_token = token
    usuario.reset_token_expira = expira
    await db.commit()
    
    # Enviar email (asíncrono, sin esperar)
    try:
        await enviar_recuperacion_contraseña(
            email_usuario=usuario.email,
            nombre_usuario=f"{usuario.nombre} {usuario.apellido}",
            token=token,
        )
    except Exception as e:
        # Log del error pero no fallar la respuesta
        print(f"Error enviando email de recuperación: {e}")
    
    return RecuperacionResponse(
        mensaje="Si el correo está registrado, recibirás un enlace de recuperación"
    )


@router.post(
    "/recuperacion/restablecer",
    response_model=UsuarioResponse,
    summary="Restablecer contraseña",
    description=(
        "Restablecer la contraseña usando el token enviado al email. "
        "El token debe ser válido y no estar expirado."
    ),
    responses={
        400: {"description": "Token inválido o expirado"},
        404: {"description": "Usuario no encontrado"},
        200: {"description": "Contraseña restablecida"},
    },
)
async def restablecer_contraseña(
    data: RestablecerContraseñaRequest,
    db: AsyncSession = Depends(get_db),
):
    """Restablecer contraseña con token de recuperación"""
    
    # Buscar usuario con ese token
    result = await db.execute(
        select(Usuario).where(Usuario.reset_token == data.token)
    )
    usuario = result.scalar_one_or_none()
    
    if not usuario:
        raise HTTPException(
            status_code=400,
            detail="Token inválido o expirado"
        )
    
    # Verificar que el token no esté expirado
    if not verificar_reset_token_vigente(usuario.reset_token_expira):
        raise HTTPException(
            status_code=400,
            detail="Token expirado. Solicita un nuevo enlace de recuperación"
        )
    
    # Cambiar contraseña
    usuario.password_hash = hash_password(data.password_nueva)
    usuario.reset_token = None  # Limpiar token
    usuario.reset_token_expira = None
    await db.commit()
    await db.refresh(usuario)
    
    return usuario


@router.patch(
    "/{usuario_id}/activar",
    response_model=UsuarioResponse,
    summary="Activar usuario",
    description="El rector activa una cuenta inactiva.",
    responses={
        404: {"description": "Usuario no encontrado"},
        400: {"description": "El usuario ya está activo"},
    },
)
async def activar_usuario(
    usuario_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_rol(Rol.ADMIN)),
):
    result = await db.execute(select(Usuario).where(Usuario.id == usuario_id))
    usuario = result.scalar_one_or_none()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if usuario.activo:
        raise HTTPException(status_code=400, detail="El usuario ya está activo")

    usuario.activo = True
    await db.commit()
    await db.refresh(usuario)
    return usuario


@router.patch(
    "/{usuario_id}/desactivar",
    response_model=UsuarioResponse,
    summary="Desactivar usuario",
    description="El rector desactiva una cuenta. El usuario no podrá iniciar sesión.",
    responses={
        404: {"description": "Usuario no encontrado"},
        400: {"description": "El usuario ya está inactivo o es el rector que hace la acción"},
    },
)
async def desactivar_usuario(
    usuario_id: UUID,
    db: AsyncSession = Depends(get_db),
    rector: Usuario = Depends(require_rol(Rol.ADMIN)),
):
    if usuario_id == rector.id:
        raise HTTPException(status_code=400, detail="No puedes desactivar tu propia cuenta")

    result = await db.execute(select(Usuario).where(Usuario.id == usuario_id))
    usuario = result.scalar_one_or_none()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if not usuario.activo:
        raise HTTPException(status_code=400, detail="El usuario ya está inactivo")

    usuario.activo = False
    await db.commit()
    await db.refresh(usuario)
    return usuario


@router.patch(
    "/{usuario_id}/rol",
    response_model=UsuarioResponse,
    summary="Cambiar rol de usuario (rector)",
    description="El rector puede cambiar el rol de cualquier usuario.",
    responses={
        404: {"description": "Usuario no encontrado"},
        400: {"description": "No puedes cambiar tu propio rol"},
    },
)
async def cambiar_rol(
    usuario_id: UUID,
    rol: Rol = Query(..., description="Nuevo rol a asignar"),
    db: AsyncSession = Depends(get_db),
    rector: Usuario = Depends(require_rol(Rol.ADMIN)),
):
    if usuario_id == rector.id:
        raise HTTPException(status_code=400, detail="No puedes cambiar tu propio rol")

    result = await db.execute(select(Usuario).where(Usuario.id == usuario_id))
    usuario = result.scalar_one_or_none()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    usuario.rol = rol
    await db.commit()
    await db.refresh(usuario)
    return usuario


@router.delete(
    "/{usuario_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar usuario (rector)",
    description=(
        "El rector elimina permanentemente un usuario. "
        "No se permite auto-eliminación. "
        "Si el usuario tiene solicitudes asociadas, usar /desactivar en su lugar."
    ),
    responses={
        204: {"description": "Usuario eliminado"},
        400: {"description": "Auto-eliminación o usuario con solicitudes"},
        403: {"description": "Solo el rector puede eliminar usuarios"},
        404: {"description": "Usuario no encontrado"},
    },
)
async def eliminar_usuario(
    usuario_id: UUID,
    db: AsyncSession = Depends(get_db),
    rector: Usuario = Depends(require_rol(Rol.ADMIN)),
):
    if usuario_id == rector.id:
        raise HTTPException(status_code=400, detail="No puedes eliminar tu propia cuenta")

    result = await db.execute(select(Usuario).where(Usuario.id == usuario_id))
    usuario = result.scalar_one_or_none()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    from app.models.solicitud import Solicitud
    count_result = await db.execute(
        select(func.count(Solicitud.id)).where(Solicitud.estudiante_id == usuario_id)
    )
    if count_result.scalar_one() > 0:
        raise HTTPException(
            status_code=400,
            detail="No se puede eliminar un usuario con solicitudes asociadas. "
                   "Usa PATCH /usuarios/{id}/desactivar en su lugar.",
        )

    await db.delete(usuario)
    await db.commit()