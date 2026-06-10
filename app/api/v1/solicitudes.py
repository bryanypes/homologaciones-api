from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from app.core.database import get_db
from app.core.deps import get_current_user, require_rol
from app.models.usuario import Usuario, Rol
from app.models.solicitud import Solicitud, EstadoSolicitud, HistorialEstado
from app.schemas.solicitud import SolicitudCreate, SolicitudResponse, CambiarEstadoRequest
from app.services.kafka_service import publicar_cambio_estado

router = APIRouter(prefix="/solicitudes", tags=["Solicitudes"])


@router.post("/", response_model=SolicitudResponse, status_code=status.HTTP_201_CREATED,
    summary="Crear solicitud",
    description="El estudiante crea una nueva solicitud. Puede usar IDs del catálogo o texto libre.",
    responses={
        201: {"description": "Solicitud creada"},
        403: {"description": "Solo estudiantes pueden crear solicitudes"},
    },
)
async def crear_solicitud(
    data: SolicitudCreate,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol(Rol.ESTUDIANTE)),
):
    solicitud = Solicitud(
        estudiante_id=usuario.id,
        programa_origen_id=data.programa_origen_id,
        programa_destino_id=data.programa_destino_id,
        institucion_origen=data.institucion_origen,
        programa_origen=data.programa_origen,
        institucion_destino=data.institucion_destino,
        programa_destino=data.programa_destino,
        estado=EstadoSolicitud.BORRADOR,
    )
    db.add(solicitud)
    await db.commit()
    await db.refresh(solicitud)
    return solicitud

@router.get(
    "/",
    response_model=list[SolicitudResponse],
    summary="Listar solicitudes",
    description="Estudiantes ven solo sus solicitudes. Coordinadores y rectores ven todas.",
)
async def listar_solicitudes(
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    if usuario.rol == Rol.ESTUDIANTE:
        result = await db.execute(
            select(Solicitud).where(Solicitud.estudiante_id == usuario.id)
        )
    else:
        result = await db.execute(select(Solicitud))
    return result.scalars().all()


@router.get(
    "/{solicitud_id}",
    response_model=SolicitudResponse,
    summary="Obtener solicitud",
    description="Retorna el detalle de una solicitud. El estudiante solo puede ver las suyas.",
    responses={
        404: {"description": "Solicitud no encontrada"},
        403: {"description": "Sin permisos para ver esta solicitud"},
    },
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


@router.patch(
    "/{solicitud_id}/enviar",
    response_model=SolicitudResponse,
    summary="Enviar solicitud",
    description="El estudiante envía su solicitud para revisión. Solo aplica si está en estado BORRADOR.",
    responses={
        400: {"description": "La solicitud no está en estado BORRADOR"},
        403: {"description": "Solo el estudiante dueño puede enviar"},
        404: {"description": "Solicitud no encontrada"},
    },
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
        raise HTTPException(status_code=400, detail="Solo se pueden enviar solicitudes en borrador")

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
    )
    return solicitud


@router.patch(
    "/{solicitud_id}/revisar",
    response_model=SolicitudResponse,
    summary="Tomar en revisión",
    description="El coordinador toma la solicitud para revisión. Solo aplica si está en estado ENVIADA.",
    responses={
        400: {"description": "La solicitud no está en estado ENVIADA"},
        403: {"description": "Solo coordinadores pueden revisar"},
        404: {"description": "Solicitud no encontrada"},
    },
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
    )
    return solicitud


@router.patch(
    "/{solicitud_id}/aprobar",
    response_model=SolicitudResponse,
    summary="Aprobar homologación",
    description="El rector aprueba la homologación generada por la IA. Solo aplica si está en estado PENDIENTE_RECTOR.",
    responses={
        400: {"description": "La solicitud no está en estado PENDIENTE_RECTOR"},
        403: {"description": "Solo el rector puede aprobar"},
        404: {"description": "Solicitud no encontrada"},
    },
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
        raise HTTPException(status_code=400, detail="La solicitud debe estar en estado PENDIENTE_RECTOR")

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
    )
    return solicitud


@router.patch(
    "/{solicitud_id}/rechazar",
    response_model=SolicitudResponse,
    summary="Rechazar homologación",
    description="El rector rechaza la homologación. Solo aplica si está en estado PENDIENTE_RECTOR.",
    responses={
        400: {"description": "La solicitud no está en estado PENDIENTE_RECTOR"},
        403: {"description": "Solo el rector puede rechazar"},
        404: {"description": "Solicitud no encontrada"},
    },
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
        raise HTTPException(status_code=400, detail="La solicitud debe estar en estado PENDIENTE_RECTOR")

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
    )
    return solicitud