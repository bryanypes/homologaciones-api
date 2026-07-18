from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from uuid import UUID
from sqlalchemy.orm import selectinload

from datetime import datetime, timezone

from app.core.database import get_db
from app.core.deps import get_current_user, require_rol
from app.models.usuario import Usuario, Rol
from app.models.solicitud import Solicitud, EstadoSolicitud, HistorialEstado
from app.models.academico import Programa, Institucion
from app.models.resolucion import ResolucionContador
from app.schemas.solicitud import SolicitudCreate, SolicitudResponse, CambiarEstadoRequest, HistorialEstadoResponse
from app.schemas.paginacion import PaginatedResponse
from app.services.email_service import notificar_cambio_estado, notificar_mercadeo_homologacion_aprobada
import asyncio
from pydantic import BaseModel
from typing import Optional as OptionalType

router = APIRouter(prefix="/solicitudes", tags=["Solicitudes"])


class InstitucionOpcionResponse(BaseModel):
    id: UUID
    nombre: str
    tipo: OptionalType[str] = None
    codigo_ies: OptionalType[str] = None

    model_config = {"from_attributes": True}


class ProgramaOpcionResponse(BaseModel):
    id: UUID
    nombre: str
    institucion_id: UUID
    institucion_nombre: OptionalType[str] = None
    codigo_snies: OptionalType[str] = None
    tipo_formacion: OptionalType[str] = None
    metodologia: OptionalType[str] = None

    model_config = {"from_attributes": True}


async def _obtener_solicitud(solicitud_id: UUID, db: AsyncSession) -> Solicitud:
    result = await db.execute(
        select(Solicitud)
        .where(Solicitud.id == solicitud_id)
        .options(
            selectinload(Solicitud.estudiante),
            selectinload(Solicitud.programa_origen_rel),
            selectinload(Solicitud.programa_destino_rel),
        )
    )
    solicitud = result.scalar_one_or_none()
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    return solicitud


async def _verificar_scope_estudiante(
    solicitud: Solicitud, usuario: Usuario
) -> None:
    if usuario.rol == Rol.ESTUDIANTE and solicitud.estudiante_id != usuario.id:
        raise HTTPException(status_code=403, detail="Sin permisos sobre esta solicitud")


@router.get(
    "/opciones/instituciones",
    response_model=list[InstitucionOpcionResponse],
    summary="Listar instituciones",
)
async def listar_instituciones(
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    result = await db.execute(
        select(Institucion).order_by(Institucion.nombre)
    )
    return result.scalars().all()


@router.get(
    "/opciones/programas",
    response_model=list[ProgramaOpcionResponse],
    summary="Listar programas",
    description=(
        "Retorna los programas disponibles. "
        "Filtrar por institucion_id para obtener solo los de una institución."
    ),
)
async def listar_programas(
    institucion_id: OptionalType[UUID] = Query(None, description="Filtrar por institución"),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    query = select(Programa).options(
        selectinload(Programa.institucion)
    ).order_by(Programa.nombre)

    if institucion_id:
        query = query.where(Programa.institucion_id == institucion_id)

    result = await db.execute(query)
    programas = result.scalars().all()

    response = []
    for prog in programas:
        data = ProgramaOpcionResponse.model_validate(prog)
        if prog.institucion:
            data.institucion_nombre = prog.institucion.nombre
        response.append(data)
    
    return response


@router.post(
    "/",
    response_model=SolicitudResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear solicitud",
    description=(
        "El estudiante crea una solicitud. Puede elegir institución y programa del catálogo "
        "O escribir texto libre si selecciona 'Otra'. La solicitud inicia en estado BORRADOR."
    ),
    responses={
        201: {"description": "Solicitud creada"},
        400: {"description": "Datos inválidos o programa no encontrado"},
        403: {"description": "Solo estudiantes pueden crear solicitudes"},
    },
)
async def crear_solicitud(
    data: SolicitudCreate,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol(Rol.ESTUDIANTE)),
):
    institucion_origen = None
    programa_origen = None
    programa_origen_id = None
    institucion_destino = None
    programa_destino = None
    programa_destino_id = None

    if data.programa_origen_id:
        result = await db.execute(
            select(Programa)
            .where(Programa.id == data.programa_origen_id)
            .options(selectinload(Programa.institucion))
        )
        prog = result.scalar_one_or_none()
        if not prog:
            raise HTTPException(status_code=400, detail="Programa origen no encontrado")
        institucion_origen = prog.institucion.nombre if prog.institucion else None
        programa_origen = prog.nombre
        programa_origen_id = prog.id

    elif data.institucion_origen_texto and data.programa_origen_texto:
        institucion_origen = data.institucion_origen_texto
        programa_origen = data.programa_origen_texto

    else:
        raise HTTPException(
            status_code=400,
            detail="Debes elegir un programa del catálogo o escribir 'Otra'"
        )

    if data.programa_destino_id:
        result = await db.execute(
            select(Programa)
            .where(Programa.id == data.programa_destino_id)
            .options(selectinload(Programa.institucion))
        )
        prog = result.scalar_one_or_none()
        if not prog:
            raise HTTPException(status_code=400, detail="Programa destino no encontrado")
        institucion_destino = prog.institucion.nombre if prog.institucion else None
        programa_destino = prog.nombre
        programa_destino_id = prog.id

    elif data.institucion_destino_texto and data.programa_destino_texto:
        institucion_destino = data.institucion_destino_texto
        programa_destino = data.programa_destino_texto

    else:
        raise HTTPException(
            status_code=400,
            detail="Debes elegir un programa destino del catálogo o escribir 'Otra'"
        )

    cedula_final = usuario.cedula
    if data.cedula and data.cedula != usuario.cedula:
        dup = await db.execute(
            select(Usuario).where(Usuario.cedula == data.cedula, Usuario.id != usuario.id)
        )
        if dup.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Ya existe un usuario registrado con esa cédula")
        usuario.cedula = data.cedula
        cedula_final = data.cedula

    telefono_final = data.telefono or usuario.telefono
    if data.telefono and data.telefono != usuario.telefono:
        usuario.telefono = data.telefono

    solicitud = Solicitud(
        estudiante_id=usuario.id,
        cedula=cedula_final,
        telefono=telefono_final,
        correo_contacto=data.correo_contacto or usuario.email,
        institucion_origen=institucion_origen,
        programa_origen=programa_origen,
        programa_origen_id=programa_origen_id,
        institucion_destino=institucion_destino,
        programa_destino=programa_destino,
        programa_destino_id=programa_destino_id,
        estado=EstadoSolicitud.BORRADOR,
    )
    db.add(solicitud)
    await db.commit()
    await db.refresh(solicitud)
    
    return solicitud


@router.get(
    "/estadisticas",
    summary="Estadísticas de solicitudes",
    description="Retorna el total de solicitudes y el conteo agrupado por estado. Solo rector.",
    responses={403: {"description": "Solo el rector puede ver estadísticas"}},
)
async def estadisticas_solicitudes(
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_rol(Rol.VICERRECTOR)),
):
    grupos = await db.execute(
        select(Solicitud.estado, func.count(Solicitud.id)).group_by(Solicitud.estado)
    )
    por_estado = {e.value: 0 for e in EstadoSolicitud}
    total = 0
    for estado, count in grupos.all():
        por_estado[estado.value] = count
        total += count

    return {"total": total, "por_estado": por_estado}


@router.get(
    "/",
    response_model=PaginatedResponse[SolicitudResponse],
    summary="Listar solicitudes",
    description=(
        "Estudiantes ven solo sus solicitudes. "
        "Coordinadores y rectores ven todas con filtros opcionales."
    ),
)
async def listar_solicitudes(
    estado: OptionalType[EstadoSolicitud] = Query(None, description="Filtrar por estado"),
    estudiante_id: OptionalType[UUID] = Query(None, description="Filtrar por estudiante (solo rector/coordinador)"),
    page: int = Query(1, ge=1, description="Número de página"),
    size: int = Query(20, ge=1, le=100, description="Resultados por página"),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    query = select(Solicitud).options(selectinload(Solicitud.estudiante))
    count_query = select(func.count(Solicitud.id))

    if usuario.rol == Rol.ESTUDIANTE:
        query = query.where(Solicitud.estudiante_id == usuario.id)
        count_query = count_query.where(Solicitud.estudiante_id == usuario.id)
    else:
        if estudiante_id:
            query = query.where(Solicitud.estudiante_id == estudiante_id)
            count_query = count_query.where(Solicitud.estudiante_id == estudiante_id)

    if estado:
        query = query.where(Solicitud.estado == estado)
        count_query = count_query.where(Solicitud.estado == estado)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    offset = (page - 1) * size
    query = query.order_by(Solicitud.creado_en.desc()).offset(offset).limit(size)
    result = await db.execute(query)
    items = result.scalars().all()

    return PaginatedResponse(total=total, page=page, size=size, items=items)


@router.get(
    "/{solicitud_id}",
    response_model=SolicitudResponse,
    summary="Obtener solicitud",
    description="Retorna el detalle de una solicitud. Estudiante solo puede ver las suyas.",
)
async def obtener_solicitud(
    solicitud_id: UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    solicitud = await _obtener_solicitud(solicitud_id, db)
    await _verificar_scope_estudiante(solicitud, usuario)
    
    return solicitud


@router.patch(
    "/{solicitud_id}",
    response_model=SolicitudResponse,
    summary="Actualizar solicitud",
    description=(
        "El estudiante puede actualizar su solicitud si está en estado BORRADOR. "
        "Puede cambiar institucion/programa eligiendo del catálogo o escribiendo texto libre."
    ),
    responses={
        400: {"description": "Solicitud no está en BORRADOR o datos inválidos"},
        403: {"description": "Sin permisos o no es propietario"},
        404: {"description": "Solicitud no encontrada"},
    },
)
async def actualizar_solicitud(
    solicitud_id: UUID,
    data: SolicitudCreate,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol(Rol.ESTUDIANTE)),
):
    solicitud = await _obtener_solicitud(solicitud_id, db)
    await _verificar_scope_estudiante(solicitud, usuario)

    if solicitud.estado != EstadoSolicitud.BORRADOR:
        raise HTTPException(
            status_code=400,
            detail="Solo se pueden editar solicitudes en estado BORRADOR"
        )

    if data.cedula is not None and data.cedula != usuario.cedula:
        dup = await db.execute(
            select(Usuario).where(Usuario.cedula == data.cedula, Usuario.id != usuario.id)
        )
        if dup.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Ya existe un usuario registrado con esa cédula")
        usuario.cedula = data.cedula
        solicitud.cedula = data.cedula
    elif data.cedula is not None:
        solicitud.cedula = data.cedula
    if data.telefono is not None:
        usuario.telefono = data.telefono
        solicitud.telefono = data.telefono
    if data.correo_contacto is not None:
        solicitud.correo_contacto = data.correo_contacto

    if data.programa_origen_id:
        result = await db.execute(
            select(Programa)
            .where(Programa.id == data.programa_origen_id)
            .options(selectinload(Programa.institucion))
        )
        prog = result.scalar_one_or_none()
        if not prog:
            raise HTTPException(status_code=400, detail="Programa origen no encontrado")
        solicitud.institucion_origen = prog.institucion.nombre if prog.institucion else None
        solicitud.programa_origen = prog.nombre
        solicitud.programa_origen_id = prog.id

    elif data.institucion_origen_texto and data.programa_origen_texto:
        solicitud.institucion_origen = data.institucion_origen_texto
        solicitud.programa_origen = data.programa_origen_texto
        solicitud.programa_origen_id = None

    if data.programa_destino_id:
        result = await db.execute(
            select(Programa)
            .where(Programa.id == data.programa_destino_id)
            .options(selectinload(Programa.institucion))
        )
        prog = result.scalar_one_or_none()
        if not prog:
            raise HTTPException(status_code=400, detail="Programa destino no encontrado")
        solicitud.institucion_destino = prog.institucion.nombre if prog.institucion else None
        solicitud.programa_destino = prog.nombre
        solicitud.programa_destino_id = prog.id

    elif data.institucion_destino_texto and data.programa_destino_texto:
        solicitud.institucion_destino = data.institucion_destino_texto
        solicitud.programa_destino = data.programa_destino_texto
        solicitud.programa_destino_id = None

    await db.commit()
    await db.refresh(solicitud)
    
    return solicitud


@router.post(
    "/{solicitud_id}/enviar",
    response_model=SolicitudResponse,
    summary="Enviar solicitud",
    description="El estudiante envía su solicitud de BORRADOR a ENVIADA.",
    responses={
        400: {"description": "Solicitud no está en BORRADOR"},
        403: {"description": "No es propietario"},
        404: {"description": "Solicitud no encontrada"},
    },
)
async def enviar_solicitud(
    solicitud_id: UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol(Rol.ESTUDIANTE)),
):
    solicitud = await _obtener_solicitud(solicitud_id, db)
    await _verificar_scope_estudiante(solicitud, usuario)

    if solicitud.estado != EstadoSolicitud.BORRADOR:
        raise HTTPException(
            status_code=400,
            detail="Solo se pueden enviar solicitudes en estado BORRADOR"
        )

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

    estudiante = solicitud.estudiante
    asyncio.create_task(notificar_cambio_estado(
        email_estudiante=estudiante.email,
        nombre_estudiante=f"{estudiante.nombre} {estudiante.apellido}",
        solicitud_id=str(solicitud.id),
        estado_anterior=EstadoSolicitud.BORRADOR.value,
        estado_nuevo=EstadoSolicitud.ENVIADA.value,
    ))

    return solicitud


@router.patch(
    "/{solicitud_id}/cambiar-estado",
    response_model=SolicitudResponse,
    summary="Cambiar estado (Coordinador/Rector)",
    description="Coordinadores y rectores cambian el estado de una solicitud.",
    responses={
        400: {"description": "Transición de estado inválida"},
        403: {"description": "Solo coordinadores y rectores pueden cambiar estado"},
        404: {"description": "Solicitud no encontrada"},
    },
)
async def cambiar_estado(
    solicitud_id: UUID,
    nuevo_estado: EstadoSolicitud = Query(..., description="Nuevo estado"),
    data: CambiarEstadoRequest = None,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol(Rol.COORDINADOR, Rol.VICERRECTOR)),
):
    solicitud = await _obtener_solicitud(solicitud_id, db)

    if solicitud.estado == nuevo_estado:
        raise HTTPException(
            status_code=400,
            detail="La solicitud ya está en ese estado"
        )

    historial = HistorialEstado(
        solicitud_id=solicitud.id,
        usuario_id=usuario.id,
        estado_anterior=solicitud.estado,
        estado_nuevo=nuevo_estado,
        observacion=data.observacion if data else None,
    )
    solicitud.estado = nuevo_estado
    if data and data.observacion:
        solicitud.observaciones = data.observacion

    db.add(historial)
    await db.commit()
    await db.refresh(solicitud)

    estudiante = solicitud.estudiante
    asyncio.create_task(notificar_cambio_estado(
        email_estudiante=estudiante.email,
        nombre_estudiante=f"{estudiante.nombre} {estudiante.apellido}",
        solicitud_id=str(solicitud.id),
        estado_anterior=historial.estado_anterior.value if historial.estado_anterior else "",
        estado_nuevo=nuevo_estado.value,
        observacion=data.observacion if data else None,
    ))

    return solicitud


@router.delete(
    "/{solicitud_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar solicitud",
    description="El estudiante puede eliminar su solicitud si está en BORRADOR.",
    responses={
        400: {"description": "Solicitud no está en BORRADOR"},
        403: {"description": "No es propietario"},
        404: {"description": "Solicitud no encontrada"},
    },
)
async def eliminar_solicitud(
    solicitud_id: UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol(Rol.ESTUDIANTE)),
):
    solicitud = await _obtener_solicitud(solicitud_id, db)
    await _verificar_scope_estudiante(solicitud, usuario)

    if solicitud.estado != EstadoSolicitud.BORRADOR:
        raise HTTPException(
            status_code=400,
            detail="Solo se pueden eliminar solicitudes en estado BORRADOR"
        )

    await db.delete(solicitud)
    await db.commit()


@router.post(
    "/{solicitud_id}/aprobar",
    response_model=SolicitudResponse,
    summary="Aprobar solicitud",
    description=(
        "El rector aprueba la solicitud de homologación. "
        "La solicitud debe estar en estado PENDIENTE_RECTOR."
    ),
    responses={
        200: {"description": "Solicitud aprobada"},
        400: {"description": "La solicitud no está en estado PENDIENTE_RECTOR"},
        403: {"description": "Solo el rector puede aprobar solicitudes"},
        404: {"description": "Solicitud no encontrada"},
    },
)
async def aprobar_solicitud(
    solicitud_id: UUID,
    data: CambiarEstadoRequest = None,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol(Rol.VICERRECTOR)),
):
    solicitud = await _obtener_solicitud(solicitud_id, db)

    if solicitud.estado != EstadoSolicitud.PENDIENTE_RECTOR:
        raise HTTPException(
            status_code=400,
            detail="La solicitud debe estar en estado PENDIENTE_RECTOR para ser aprobada",
        )

    anio_actual = datetime.now(timezone.utc).year
    result_cnt = await db.execute(
        select(ResolucionContador).where(ResolucionContador.anio == anio_actual)
    )
    contador = result_cnt.scalar_one_or_none()
    if not contador:
        contador = ResolucionContador(anio=anio_actual, ultimo_numero=0)
        db.add(contador)
        await db.flush()
    contador.ultimo_numero += 1
    solicitud.numero_resolucion = f"{contador.ultimo_numero:04d}-{anio_actual}"

    historial = HistorialEstado(
        solicitud_id=solicitud.id,
        usuario_id=usuario.id,
        estado_anterior=solicitud.estado,
        estado_nuevo=EstadoSolicitud.APROBADA,
        observacion=data.observacion if data else None,
    )
    solicitud.estado = EstadoSolicitud.APROBADA
    if data and data.observacion:
        solicitud.observaciones = data.observacion

    db.add(historial)
    await db.commit()
    await db.refresh(solicitud)

    estudiante = solicitud.estudiante
    asyncio.create_task(notificar_cambio_estado(
        email_estudiante=estudiante.email,
        nombre_estudiante=f"{estudiante.nombre} {estudiante.apellido}",
        solicitud_id=str(solicitud.id),
        estado_anterior=EstadoSolicitud.PENDIENTE_RECTOR.value,
        estado_nuevo=EstadoSolicitud.APROBADA.value,
        observacion=data.observacion if data else None,
    ))
    asyncio.create_task(notificar_mercadeo_homologacion_aprobada(
        nombre_estudiante=f"{estudiante.nombre} {estudiante.apellido}",
        solicitud_id=str(solicitud.id),
        numero_resolucion=solicitud.numero_resolucion or "",
        programa_destino=solicitud.programa_destino or "",
        institucion_origen=solicitud.institucion_origen or "",
    ))

    return solicitud


@router.post(
    "/{solicitud_id}/rechazar",
    response_model=SolicitudResponse,
    summary="Rechazar solicitud",
    description=(
        "El rector rechaza la solicitud de homologación. "
        "La solicitud debe estar en estado PENDIENTE_RECTOR."
    ),
    responses={
        200: {"description": "Solicitud rechazada"},
        400: {"description": "La solicitud no está en estado PENDIENTE_RECTOR"},
        403: {"description": "Solo el rector puede rechazar solicitudes"},
        404: {"description": "Solicitud no encontrada"},
    },
)
async def rechazar_solicitud(
    solicitud_id: UUID,
    data: CambiarEstadoRequest = None,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol(Rol.VICERRECTOR)),
):
    solicitud = await _obtener_solicitud(solicitud_id, db)

    if solicitud.estado != EstadoSolicitud.PENDIENTE_RECTOR:
        raise HTTPException(
            status_code=400,
            detail="La solicitud debe estar en estado PENDIENTE_RECTOR para ser rechazada",
        )

    historial = HistorialEstado(
        solicitud_id=solicitud.id,
        usuario_id=usuario.id,
        estado_anterior=solicitud.estado,
        estado_nuevo=EstadoSolicitud.RECHAZADA,
        observacion=data.observacion if data else None,
    )
    solicitud.estado = EstadoSolicitud.RECHAZADA
    if data and data.observacion:
        solicitud.observaciones = data.observacion

    db.add(historial)
    await db.commit()
    await db.refresh(solicitud)

    estudiante = solicitud.estudiante
    asyncio.create_task(notificar_cambio_estado(
        email_estudiante=estudiante.email,
        nombre_estudiante=f"{estudiante.nombre} {estudiante.apellido}",
        solicitud_id=str(solicitud.id),
        estado_anterior=EstadoSolicitud.PENDIENTE_RECTOR.value,
        estado_nuevo=EstadoSolicitud.RECHAZADA.value,
        observacion=data.observacion if data else None,
    ))

    return solicitud


@router.get(
    "/{solicitud_id}/historial",
    response_model=list[HistorialEstadoResponse],
    summary="Ver historial de estados",
    description=(
        "Retorna el historial de cambios de estado de una solicitud en orden cronológico. "
        "Incluye quién realizó cada cambio y la observación asociada. "
        "El estudiante solo puede ver el historial de sus propias solicitudes."
    ),
    responses={
        403: {"description": "Sin permisos sobre esta solicitud"},
        404: {"description": "Solicitud no encontrada"},
    },
)
async def obtener_historial(
    solicitud_id: UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    solicitud = await _obtener_solicitud(solicitud_id, db)
    await _verificar_scope_estudiante(solicitud, usuario)

    result = await db.execute(
        select(HistorialEstado)
        .where(HistorialEstado.solicitud_id == solicitud_id)
        .options(selectinload(HistorialEstado.usuario))
        .order_by(HistorialEstado.creado_en.asc())
    )
    entradas = result.scalars().all()

    return [
        HistorialEstadoResponse(
            id=h.id,
            estado_anterior=h.estado_anterior,
            estado_nuevo=h.estado_nuevo,
            observacion=h.observacion,
            creado_en=h.creado_en,
            usuario_id=h.usuario_id,
            usuario_nombre=f"{h.usuario.nombre} {h.usuario.apellido}" if h.usuario else None,
        )
        for h in entradas
    ]