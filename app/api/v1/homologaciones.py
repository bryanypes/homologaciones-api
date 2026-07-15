import os
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
from uuid import UUID
from fastapi.responses import FileResponse
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.deps import get_current_user, require_rol
from app.models.usuario import Usuario, Rol
from app.models.solicitud import Solicitud, EstadoSolicitud, HistorialEstado
from app.models.documento import Documento, TipoDocumento
from app.models.homologacion import Homologacion, HomologacionAsignatura, EstadoAsignatura
from app.schemas.homologacion import (
    HomologacionResponse,
    HomologacionAsignaturaResponse,
    ActualizarAsignaturaRequest,
)
import asyncio
from app.services.ai_service import procesar_homologacion
from app.services.doc_service import generar_resolucion_docx
from app.services.email_service import notificar_homologacion_completada

router = APIRouter(prefix="/homologaciones", tags=["Homologaciones"])


@router.post(
    "/{solicitud_id}/procesar",
    response_model=HomologacionResponse,
    summary="Procesar homologación con IA",
    description=(
        "El coordinador activa el procesamiento con IA. "
        "Requiere que el estudiante haya subido sus notas "
        "y que el coordinador haya subido el pensum destino. "
        "La solicitud debe estar en estado EN_REVISION o REVISION_COORDINADOR. "
        "Si ya existe una homologación previa (reprocesamiento), se elimina antes de crear la nueva."
    ),
    responses={
        200: {"description": "Homologación procesada exitosamente"},
        400: {"description": "Estado incorrecto o documentos faltantes"},
        403: {"description": "Solo coordinadores pueden activar el procesamiento"},
        404: {"description": "Solicitud no encontrada"},
        500: {"description": "Error en el procesamiento con IA"},
    },
)
async def procesar(
    solicitud_id: UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol(Rol.COORDINADOR)),
):
    result = await db.execute(
        select(Solicitud)
        .where(Solicitud.id == solicitud_id)
        .options(selectinload(Solicitud.estudiante))
    )
    solicitud = result.scalar_one_or_none()

    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    estados_permitidos = [EstadoSolicitud.EN_REVISION, EstadoSolicitud.REVISION_COORDINADOR]
    if solicitud.estado not in estados_permitidos:
        raise HTTPException(
            status_code=400,
            detail="La solicitud debe estar en estado EN_REVISION o REVISION_COORDINADOR para procesar con IA",
        )

    result_docs = await db.execute(
        select(Documento).where(Documento.solicitud_id == solicitud_id)
    )
    documentos = result_docs.scalars().all()

    docs_origen = [d for d in documentos if d.tipo == TipoDocumento.PENSUM_ORIGEN]
    docs_destino = [d for d in documentos if d.tipo == TipoDocumento.PENSUM_DESTINO]

    if not docs_origen:
        raise HTTPException(
            status_code=400,
            detail="Falta el certificado de notas del estudiante. "
                   "El estudiante debe subirlo en POST /documentos/{id}/notas",
        )

    if not docs_destino:
        raise HTTPException(
            status_code=400,
            detail="Falta el pensum del programa destino. "
                   "El coordinador debe subirlo en POST /documentos/{id}/pensum-destino",
        )

    # Si es un reprocesamiento, eliminar la homologación previa y sus asignaturas
    if solicitud.estado == EstadoSolicitud.REVISION_COORDINADOR:
        result_hom = await db.execute(
            select(Homologacion).where(Homologacion.solicitud_id == solicitud_id)
        )
        hom_existente = result_hom.scalar_one_or_none()
        if hom_existente:
            await db.execute(
                delete(HomologacionAsignatura).where(
                    HomologacionAsignatura.homologacion_id == hom_existente.id
                )
            )
            await db.delete(hom_existente)
            await db.flush()

    historial = HistorialEstado(
        solicitud_id=solicitud.id,
        usuario_id=usuario.id,
        estado_anterior=solicitud.estado,
        estado_nuevo=EstadoSolicitud.PROCESANDO_IA,
    )
    solicitud.estado = EstadoSolicitud.PROCESANDO_IA
    db.add(historial)
    await db.commit()

    estudiante = solicitud.estudiante
    nombre_estudiante = f"{estudiante.nombre} {estudiante.apellido}"

    try:
        resultado = await procesar_homologacion(
            rutas_origen=[d.ruta for d in docs_origen],
            ruta_destino=docs_destino[0].ruta,
            nombre_estudiante=nombre_estudiante,
        )
    except Exception as e:
        solicitud.estado = EstadoSolicitud.EN_REVISION
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Error al procesar con IA: {str(e)}")

    homologacion = Homologacion(
        solicitud_id=solicitud.id,
        resumen_ia=resultado["resumen"],
        tokens_utilizados=resultado["tokens_utilizados"],
    )
    db.add(homologacion)
    await db.flush()

    for item in resultado["asignaturas"]:
        estado_ia = EstadoAsignatura(item["estado"].lower())
        db.add(HomologacionAsignatura(
            homologacion_id=homologacion.id,
            asignatura_origen=item["asignatura_origen"],
            creditos_origen=item.get("creditos_origen"),
            calificacion_origen=item.get("calificacion_origen"),
            asignatura_destino=item.get("asignatura_destino"),
            codigo_destino=item.get("codigo_destino"),
            semestre_destino=item.get("semestre_destino"),
            creditos_destino=item.get("creditos_destino"),
            intensidad_horaria_destino=item.get("intensidad_horaria_destino"),
            tipo_destino=item.get("tipo_destino"),
            estado=estado_ia,
            estado_ia_original=estado_ia,
            fue_corregida=False,
            justificacion=item.get("justificacion"),
            similitud_porcentaje=item.get("similitud_porcentaje"),
        ))

    historial2 = HistorialEstado(
        solicitud_id=solicitud.id,
        usuario_id=usuario.id,
        estado_anterior=EstadoSolicitud.PROCESANDO_IA,
        estado_nuevo=EstadoSolicitud.REVISION_COORDINADOR,
    )
    solicitud.estado = EstadoSolicitud.REVISION_COORDINADOR
    db.add(historial2)
    await db.commit()

    asyncio.create_task(notificar_homologacion_completada(
        email_estudiante=estudiante.email,
        nombre_estudiante=f"{estudiante.nombre} {estudiante.apellido}",
        solicitud_id=str(solicitud.id),
        tokens_utilizados=resultado["tokens_utilizados"],
    ))

    result_final = await db.execute(
        select(Homologacion)
        .where(Homologacion.id == homologacion.id)
        .options(selectinload(Homologacion.asignaturas))
    )
    return result_final.scalar_one()


@router.patch(
    "/{solicitud_id}/asignaturas/{asignatura_id}",
    response_model=HomologacionAsignaturaResponse,
    summary="Actualizar estado de una asignatura",
    description="El coordinador puede modificar el estado y justificación de una asignatura individual.",
    responses={
        200: {"description": "Asignatura actualizada"},
        404: {"description": "Homologación o asignatura no encontrada"},
        403: {"description": "Solo coordinadores pueden modificar asignaturas"},
    },
)
async def actualizar_asignatura(
    solicitud_id: UUID,
    asignatura_id: UUID,
    body: ActualizarAsignaturaRequest,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol(Rol.COORDINADOR, Rol.RECTOR)),
):
    result = await db.execute(
        select(Homologacion).where(Homologacion.solicitud_id == solicitud_id)
    )
    homologacion = result.scalar_one_or_none()
    if not homologacion:
        raise HTTPException(status_code=404, detail="Homologación no encontrada")

    result_asig = await db.execute(
        select(HomologacionAsignatura).where(
            HomologacionAsignatura.id == asignatura_id,
            HomologacionAsignatura.homologacion_id == homologacion.id,
        )
    )
    asignatura = result_asig.scalar_one_or_none()
    if not asignatura:
        raise HTTPException(status_code=404, detail="Asignatura no encontrada")

    asignatura.estado = body.estado
    if body.justificacion is not None:
        asignatura.justificacion = body.justificacion
    if asignatura.estado_ia_original is not None:
        asignatura.fue_corregida = (body.estado != asignatura.estado_ia_original)

    await db.commit()
    await db.refresh(asignatura)
    return asignatura


@router.post(
    "/{solicitud_id}/enviar-rector",
    status_code=status.HTTP_200_OK,
    summary="Enviar homologación al rector",
    description=(
        "El coordinador envía la homologación revisada al rector para su aprobación. "
        "La solicitud debe estar en estado REVISION_COORDINADOR."
    ),
    responses={
        200: {"description": "Homologación enviada al rector"},
        400: {"description": "La solicitud no está en estado REVISION_COORDINADOR"},
        403: {"description": "Solo coordinadores pueden enviar al rector"},
        404: {"description": "Solicitud no encontrada"},
    },
)
async def enviar_rector(
    solicitud_id: UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol(Rol.COORDINADOR)),
):
    result = await db.execute(
        select(Solicitud).where(Solicitud.id == solicitud_id)
    )
    solicitud = result.scalar_one_or_none()
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    if solicitud.estado != EstadoSolicitud.REVISION_COORDINADOR:
        raise HTTPException(
            status_code=400,
            detail="La solicitud debe estar en estado REVISION_COORDINADOR para enviar al rector",
        )

    historial = HistorialEstado(
        solicitud_id=solicitud.id,
        usuario_id=usuario.id,
        estado_anterior=solicitud.estado,
        estado_nuevo=EstadoSolicitud.PENDIENTE_RECTOR,
    )
    solicitud.estado = EstadoSolicitud.PENDIENTE_RECTOR
    db.add(historial)
    await db.commit()

    return {"mensaje": "Homologación enviada al rector correctamente"}


@router.get(
    "/estadisticas-ia",
    summary="Estadísticas de precisión de la IA",
    description=(
        "Retorna métricas sobre qué tan seguido el coordinador corrige las decisiones de la IA. "
        "Útil para medir la calidad del modelo. Solo para coordinadores y rectores."
    ),
    responses={403: {"description": "Sin permisos"}},
)
async def estadisticas_ia(
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_rol(Rol.COORDINADOR, Rol.RECTOR)),
):
    result_total = await db.execute(
        select(
            HomologacionAsignatura.estado_ia_original,
            func.count(HomologacionAsignatura.id).label("total"),
        )
        .where(HomologacionAsignatura.estado_ia_original.is_not(None))
        .group_by(HomologacionAsignatura.estado_ia_original)
    )
    result_corr = await db.execute(
        select(
            HomologacionAsignatura.estado_ia_original,
            func.count(HomologacionAsignatura.id).label("corregidas"),
        )
        .where(
            HomologacionAsignatura.estado_ia_original.is_not(None),
            HomologacionAsignatura.fue_corregida.is_(True),
        )
        .group_by(HomologacionAsignatura.estado_ia_original)
    )
    totales = {r.estado_ia_original: r.total for r in result_total.all()}
    corregidas_por_estado = {r.estado_ia_original: r.corregidas for r in result_corr.all()}

    total_global = sum(totales.values())
    corregidas_global = sum(corregidas_por_estado.values())
    precision = round(1 - corregidas_global / total_global, 4) if total_global > 0 else None

    por_estado = {
        estado.value: {
            "total": total,
            "corregidas": corregidas_por_estado.get(estado, 0),
            "precision": round(1 - corregidas_por_estado.get(estado, 0) / total, 4) if total > 0 else None,
        }
        for estado, total in totales.items()
    }

    return {
        "total_asignaturas_procesadas": total_global,
        "corregidas_por_coordinador": corregidas_global,
        "precision_ia": precision,
        "por_estado_ia": por_estado,
    }


@router.get(
    "/{solicitud_id}",
    response_model=HomologacionResponse,
    summary="Obtener homologación",
    description="Retorna el resultado del análisis de homologación. Accesible por coordinador y rector.",
    responses={
        404: {"description": "Homologación no encontrada"},
        403: {"description": "Sin permisos"},
    },
)
async def obtener_homologacion(
    solicitud_id: UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol(Rol.COORDINADOR, Rol.RECTOR)),
):
    result = await db.execute(
        select(Homologacion)
        .where(Homologacion.solicitud_id == solicitud_id)
        .options(selectinload(Homologacion.asignaturas))
    )
    homologacion = result.scalar_one_or_none()

    if not homologacion:
        raise HTTPException(status_code=404, detail="Homologación no encontrada")

    return homologacion


@router.post(
    "/{solicitud_id}/generar-resolucion",
    summary="Generar resolución Word",
    description="Descarga la resolución de homologación en formato Word (.docx). Solo disponible para solicitudes aprobadas. El estudiante solo puede descargar la resolución de sus propias solicitudes.",
    responses={
        200: {"description": "Archivo Word generado"},
        400: {"description": "La solicitud no está aprobada"},
        403: {"description": "Sin permisos sobre esta solicitud"},
        404: {"description": "Solicitud u homologación no encontrada"},
    },
)
async def generar_resolucion(
    solicitud_id: UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    result_sol = await db.execute(
        select(Solicitud)
        .where(Solicitud.id == solicitud_id)
        .options(selectinload(Solicitud.estudiante))
    )
    solicitud = result_sol.scalar_one_or_none()

    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    if usuario.rol == Rol.ESTUDIANTE:
        if solicitud.estudiante_id != usuario.id:
            raise HTTPException(status_code=403, detail="Sin permisos sobre esta solicitud")
        if solicitud.estado != EstadoSolicitud.APROBADA:
            raise HTTPException(
                status_code=400,
                detail="La resolución solo está disponible para solicitudes aprobadas",
            )
    elif usuario.rol == Rol.COORDINADOR:
        estados_coordinador = {
            EstadoSolicitud.REVISION_COORDINADOR,
            EstadoSolicitud.PENDIENTE_RECTOR,
            EstadoSolicitud.APROBADA,
        }
        if solicitud.estado not in estados_coordinador:
            raise HTTPException(
                status_code=400,
                detail="La resolución solo está disponible en estados REVISION_COORDINADOR, PENDIENTE_RECTOR o APROBADA",
            )
    elif usuario.rol == Rol.RECTOR:
        estados_rector = {EstadoSolicitud.PENDIENTE_RECTOR, EstadoSolicitud.APROBADA}
        if solicitud.estado not in estados_rector:
            raise HTTPException(
                status_code=400,
                detail="La resolución solo está disponible en estados PENDIENTE_RECTOR o APROBADA",
            )

    # Verificar si ya existe una resolución subida manualmente
    result_res = await db.execute(
        select(Documento).where(
            Documento.solicitud_id == solicitud_id,
            Documento.tipo == TipoDocumento.RESOLUCION,
        )
    )
    doc_resolucion = result_res.scalar_one_or_none()
    if doc_resolucion and os.path.exists(doc_resolucion.ruta):
        return FileResponse(
            path=doc_resolucion.ruta,
            media_type=doc_resolucion.mime_type,
            filename=doc_resolucion.nombre_original,
        )

    result = await db.execute(
        select(Homologacion)
        .where(Homologacion.solicitud_id == solicitud_id)
        .options(selectinload(Homologacion.asignaturas))
    )
    homologacion = result.scalar_one_or_none()

    if not homologacion:
        raise HTTPException(status_code=404, detail="Homologación no encontrada")

    ruta = generar_resolucion_docx(homologacion, solicitud)

    return FileResponse(
        path=ruta,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"resolucion_homologacion_{solicitud_id}.docx",
    )
