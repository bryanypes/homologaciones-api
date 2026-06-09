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

router = APIRouter(prefix="/solicitudes", tags=["solicitudes"])


@router.post("/", response_model=SolicitudResponse, status_code=status.HTTP_201_CREATED)
async def crear_solicitud(
    data: SolicitudCreate,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol(Rol.ESTUDIANTE)),
):
    solicitud = Solicitud(
        estudiante_id=usuario.id,
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


@router.get("/", response_model=list[SolicitudResponse])
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


@router.get("/{solicitud_id}", response_model=SolicitudResponse)
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


@router.patch("/{solicitud_id}/enviar", response_model=SolicitudResponse)
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


@router.patch("/{solicitud_id}/revisar", response_model=SolicitudResponse)
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


@router.patch("/{solicitud_id}/rechazar", response_model=SolicitudResponse)
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


@router.patch("/{solicitud_id}/aprobar", response_model=SolicitudResponse)
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