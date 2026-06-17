from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from uuid import UUID
from typing import Optional
from datetime import date

from app.core.database import get_db
from app.core.deps import get_current_user, require_rol
from app.models.usuario import Usuario, Rol
from app.models.solicitud import Solicitud, EstadoSolicitud, HistorialEstado
from app.models.documento import Documento, TipoDocumento
from app.models.academico import Programa, Institucion
from app.schemas.solicitud import SolicitudCreate, SolicitudResponse, CambiarEstadoRequest
from app.schemas.paginacion import PaginatedResponse
from app.services.kafka_service import publicar_cambio_estado

router = APIRouter(prefix="/solicitudes", tags=["Solicitudes"])


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

async def _poblar_desde_catalogo(
    db: AsyncSession, programa_id, texto_nombre, texto_institucion
):
    if not programa_id:
        return texto_nombre, texto_institucion
    result = await db.execute(
        select(Programa)
        .where(Programa.id == programa_id)
        .options(selectinload(Programa.institucion))
    )
    prog = result.scalar_one_or_none()
    if prog:
        return prog.nombre, (prog.institucion.nombre if prog.institucion else texto_institucion)
    return texto_nombre, texto_institucion


async def _buscar_programa_por_nombre(
    db: AsyncSession,
    nombre: Optional[str],
    nombre_institucion: Optional[str],
) -> Optional[UUID]:
    """
    Busca un programa por nombre (ilike) y opcionalmente filtra por institución.
    Retorna el ID del primer match o None.
    """
    if not nombre:
        return None

    stmt = select(Programa).where(Programa.nombre.ilike(nombre))

    if nombre_institucion:
        stmt = stmt.join(Programa.institucion).where(
            Institucion.nombre.ilike(nombre_institucion)
        )

    result = await db.execute(stmt.limit(1))
    prog = result.scalars().first()
    return prog.id if prog else None


async def _verificar_notas_subidas(db: AsyncSession, solicitud_id: UUID) -> None:
    """
    Verifica que el estudiante haya subido su certificado de notas (pensum_origen).
    El pensum_destino lo sube el coordinador después — no se valida aquí.
    """
    result = await db.execute(
        select(Documento.tipo).where(Documento.solicitud_id == solicitud_id)
    )
    tipos = {row[0] for row in result.fetchall()}

    if TipoDocumento.PENSUM_ORIGEN not in tipos:
        raise HTTPException(
            status_code=400,
            detail="Debes subir tu certificado de notas antes de enviar la solicitud. "
                   "Usa el endpoint POST /documentos/{id}/notas",
        )


async def _verificar_ambos_pdfs(db: AsyncSession, solicitud_id: UUID) -> None:
    """
    Verifica que existan AMBOS PDFs antes de activar la IA.
    Llamado desde homologaciones.py al procesar.
    """
    result = await db.execute(
        select(Documento.tipo).where(Documento.solicitud_id == solicitud_id)
    )
    tipos = {row[0] for row in result.fetchall()}
    faltantes = []
    if TipoDocumento.PENSUM_ORIGEN not in tipos:
        faltantes.append("certificado de notas del estudiante")
    if TipoDocumento.PENSUM_DESTINO not in tipos:
        faltantes.append("pensum del programa destino")
    if faltantes:
        raise HTTPException(
            status_code=400,
            detail=f"Faltan documentos para procesar con IA: {', '.join(faltantes)}",
        )


# ──────────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.post(
    "/",
    response_model=SolicitudResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear solicitud",
    description="El estudiante crea una nueva solicitud de homologación.",
)
async def crear_solicitud(
    data: SolicitudCreate,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol(Rol.ESTUDIANTE)),
):
    programa_origen_id = data.programa_origen_id
    programa_destino_id = data.programa_destino_id

    # Buscar por nombre + institución si no se proporcionó ID
    if not programa_origen_id:
        programa_origen_id = await _buscar_programa_por_nombre(
            db, data.programa_origen, data.institucion_origen
        )

    if not programa_destino_id:
        programa_destino_id = await _buscar_programa_por_nombre(
            db, data.programa_destino, data.institucion_destino
        )

    programa_origen, institucion_origen = await _poblar_desde_catalogo(
        db, programa_origen_id, data.programa_origen, data.institucion_origen
    )
    programa_destino, institucion_destino = await _poblar_desde_catalogo(
        db, programa_destino_id, data.programa_destino, data.institucion_destino
    )

    solicitud = Solicitud(
        estudiante_id=usuario.id,
        cedula=data.cedula,
        telefono=data.telefono,
        correo_contacto=data.correo_contacto,
        programa_origen_id=programa_origen_id,
        programa_destino_id=programa_destino_id,
        institucion_origen=institucion_origen,
        programa_origen=programa_origen,
        institucion_destino=institucion_destino,
        programa_destino=programa_destino,
        estado=EstadoSolicitud.BORRADOR,
    )
    db.add(solicitud)
    await db.commit()
    await db.refresh(solicitud)
    return solicitud


@router.get(
    "/",
    response_model=PaginatedResponse[SolicitudResponse],
    summary="Listar solicitudes",
    description=(
        "Estudiantes ven solo las suyas. Coordinadores y rectores ven todas. "
        "Filtros: estado, programa destino, fecha. Paginación incluida."
    ),
)
async def listar_solicitudes(
    estado: Optional[EstadoSolicitud] = Query(None),
    programa_destino_id: Optional[UUID] = Query(None),
    fecha_desde: Optional[date] = Query(None),
    fecha_hasta: Optional[date] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    query = select(Solicitud)
    count_query = select(func.count(Solicitud.id))

    if usuario.rol == Rol.ESTUDIANTE:
        query = query.where(Solicitud.estudiante_id == usuario.id)
        count_query = count_query.where(Solicitud.estudiante_id == usuario.id)

    if estado is not None:
        query = query.where(Solicitud.estado == estado)
        count_query = count_query.where(Solicitud.estado == estado)
    if programa_destino_id is not None:
        query = query.where(Solicitud.programa_destino_id == programa_destino_id)
        count_query = count_query.where(Solicitud.programa_destino_id == programa_destino_id)
    if fecha_desde is not None:
        query = query.where(Solicitud.creado_en >= fecha_desde)
        count_query = count_query.where(Solicitud.creado_en >= fecha_desde)
    if fecha_hasta is not None:
        query = query.where(Solicitud.creado_en <= fecha_hasta)
        count_query = count_query.where(Solicitud.creado_en <= fecha_hasta)

    total = (await db.execute(count_query)).scalar_one()
    offset = (page - 1) * size
    items = (await db.execute(
        query.order_by(Solicitud.creado_en.desc()).offset(offset).limit(size)
    )).scalars().all()

    return PaginatedResponse(total=total, page=page, size=size, items=items)


@router.get(
    "/{solicitud_id}",
    response_model=SolicitudResponse,
    summary="Obtener solicitud",
)
async def obtener_solicitud(
    solicitud_id: UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(Solicitud).where(Solicitud.id == solicitud_id))
    solicitud = result.scalar_one_or_none()
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if usuario.rol == Rol.ESTUDIANTE and solicitud.estudiante_id != usuario.id:
        raise HTTPException(status_code=403, detail="Sin permisos")
    return solicitud


@router.get(
    "/{solicitud_id}/historial",
    summary="Historial de estados",
)
async def historial_solicitud(
    solicitud_id: UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(Solicitud).where(Solicitud.id == solicitud_id))
    solicitud = result.scalar_one_or_none()
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if usuario.rol == Rol.ESTUDIANTE and solicitud.estudiante_id != usuario.id:
        raise HTTPException(status_code=403, detail="Sin permisos")

    result_h = await db.execute(
        select(HistorialEstado)
        .where(HistorialEstado.solicitud_id == solicitud_id)
        .order_by(HistorialEstado.creado_en.asc())
    )
    return result_h.scalars().all()


@router.patch(
    "/{solicitud_id}/enviar",
    response_model=SolicitudResponse,
    summary="Enviar solicitud",
    description=(
        "El estudiante envía la solicitud para revisión. "
        "**Requiere que el certificado de notas esté subido.** "
        "El coordinador subirá el pensum destino después."
    ),
)
async def enviar_solicitud(
    solicitud_id: UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol(Rol.ESTUDIANTE)),
):
    result = await db.execute(select(Solicitud).where(Solicitud.id == solicitud_id))
    solicitud = result.scalar_one_or_none()
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if solicitud.estudiante_id != usuario.id:
        raise HTTPException(status_code=403, detail="Sin permisos")
    if solicitud.estado != EstadoSolicitud.BORRADOR:
        raise HTTPException(status_code=400, detail="Solo se pueden enviar solicitudes en BORRADOR")

    await _verificar_notas_subidas(db, solicitud_id)

    historial = HistorialEstado(
        solicitud_id=solicitud.id,
        usuario_id=usuario.id,
        estado_anterior=solicitud.estado,
        estado_nuevo=EstadoSolicitud.ENVIADA,
    )
    solicitud.estado = EstadoSolicitud.ENVIADA
    db.add(historial)
    await db.commit()
    await db.refresh(solicitud)
    publicar_cambio_estado(
        solicitud_id=str(solicitud.id),
        estado_anterior=EstadoSolicitud.BORRADOR.value,
        estado_nuevo=EstadoSolicitud.ENVIADA.value,
        usuario_id=str(usuario.id),
        email_estudiante=getattr(solicitud, "correo_contacto", "") or "",
        nombre_estudiante=f"{usuario.nombre} {usuario.apellido}",
    )
    return solicitud


@router.patch(
    "/{solicitud_id}/revisar",
    response_model=SolicitudResponse,
    summary="Tomar en revisión",
    description=(
        "El coordinador toma la solicitud. "
        "Después de esto debe subir el pensum destino antes de activar la IA."
    ),
)
async def tomar_revision(
    solicitud_id: UUID,
    data: CambiarEstadoRequest,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol(Rol.COORDINADOR)),
):
    result = await db.execute(select(Solicitud).where(Solicitud.id == solicitud_id))
    solicitud = result.scalar_one_or_none()
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if solicitud.estado != EstadoSolicitud.ENVIADA:
        raise HTTPException(status_code=400, detail="La solicitud debe estar en estado ENVIADA")

    historial = HistorialEstado(
        solicitud_id=solicitud.id,
        usuario_id=usuario.id,
        estado_anterior=solicitud.estado,
        estado_nuevo=EstadoSolicitud.EN_REVISION,
        observacion=data.observacion,
    )
    solicitud.estado = EstadoSolicitud.EN_REVISION
    db.add(historial)
    await db.commit()
    await db.refresh(solicitud)
    publicar_cambio_estado(
        solicitud_id=str(solicitud.id),
        estado_anterior=EstadoSolicitud.ENVIADA.value,
        estado_nuevo=EstadoSolicitud.EN_REVISION.value,
        usuario_id=str(usuario.id),
        email_estudiante=getattr(solicitud, "correo_contacto", "") or "",
        nombre_estudiante="",
    )
    return solicitud


@router.patch(
    "/{solicitud_id}/aprobar",
    response_model=SolicitudResponse,
    summary="Aprobar homologación",
)
async def aprobar_solicitud(
    solicitud_id: UUID,
    data: CambiarEstadoRequest,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol(Rol.RECTOR)),
):
    result = await db.execute(select(Solicitud).where(Solicitud.id == solicitud_id))
    solicitud = result.scalar_one_or_none()
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if solicitud.estado != EstadoSolicitud.PENDIENTE_RECTOR:
        raise HTTPException(status_code=400, detail="La solicitud debe estar en PENDIENTE_RECTOR")

    historial = HistorialEstado(
        solicitud_id=solicitud.id,
        usuario_id=usuario.id,
        estado_anterior=solicitud.estado,
        estado_nuevo=EstadoSolicitud.APROBADA,
        observacion=data.observacion,
    )
    solicitud.estado = EstadoSolicitud.APROBADA
    db.add(historial)
    await db.commit()
    await db.refresh(solicitud)
    publicar_cambio_estado(
        solicitud_id=str(solicitud.id),
        estado_anterior=EstadoSolicitud.PENDIENTE_RECTOR.value,
        estado_nuevo=EstadoSolicitud.APROBADA.value,
        usuario_id=str(usuario.id),
        email_estudiante=getattr(solicitud, "correo_contacto", "") or "",
        nombre_estudiante="",
        observacion=data.observacion,
    )
    return solicitud


@router.patch(
    "/{solicitud_id}/rechazar",
    response_model=SolicitudResponse,
    summary="Rechazar homologación",
)
async def rechazar_solicitud(
    solicitud_id: UUID,
    data: CambiarEstadoRequest,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol(Rol.RECTOR)),
):
    result = await db.execute(select(Solicitud).where(Solicitud.id == solicitud_id))
    solicitud = result.scalar_one_or_none()
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if solicitud.estado != EstadoSolicitud.PENDIENTE_RECTOR:
        raise HTTPException(status_code=400, detail="La solicitud debe estar en PENDIENTE_RECTOR")

    historial = HistorialEstado(
        solicitud_id=solicitud.id,
        usuario_id=usuario.id,
        estado_anterior=solicitud.estado,
        estado_nuevo=EstadoSolicitud.RECHAZADA,
        observacion=data.observacion,
    )
    solicitud.estado = EstadoSolicitud.RECHAZADA
    db.add(historial)
    await db.commit()
    await db.refresh(solicitud)
    publicar_cambio_estado(
        solicitud_id=str(solicitud.id),
        estado_anterior=EstadoSolicitud.PENDIENTE_RECTOR.value,
        estado_nuevo=EstadoSolicitud.RECHAZADA.value,
        usuario_id=str(usuario.id),
        email_estudiante=getattr(solicitud, "correo_contacto", "") or "",
        nombre_estudiante="",
        observacion=data.observacion,
    )
    return solicitud