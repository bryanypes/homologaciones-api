from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from fastapi.responses import FileResponse
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.deps import get_current_user, require_rol
from app.models.usuario import Usuario, Rol
from app.models.solicitud import Solicitud, EstadoSolicitud, HistorialEstado
from app.models.documento import Documento, TipoDocumento
from app.models.homologacion import Homologacion, HomologacionAsignatura, EstadoAsignatura
from app.schemas.homologacion import HomologacionResponse
from app.services.ai_service import procesar_homologacion
from app.services.doc_service import generar_resolucion_docx
from app.services.kafka_service import publicar_homologacion_completada

router = APIRouter(prefix="/homologaciones", tags=["Homologaciones"])


@router.post(
    "/{solicitud_id}/procesar",
    response_model=HomologacionResponse,
    summary="Procesar homologación con IA",
    description=(
        "El coordinador activa el procesamiento con IA. "
        "Requiere que el estudiante haya subido sus notas "
        "y que el coordinador haya subido el pensum destino. "
        "La solicitud debe estar en estado EN_REVISION."
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
    # Verificar solicitud
    result = await db.execute(
        select(Solicitud)
        .where(Solicitud.id == solicitud_id)
        .options(selectinload(Solicitud.estudiante))
    )
    solicitud = result.scalar_one_or_none()

    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    if solicitud.estado != EstadoSolicitud.EN_REVISION:
        raise HTTPException(
            status_code=400,
            detail="La solicitud debe estar en estado EN_REVISION para procesar con IA"
        )

    # Verificar que existan ambos documentos
    result_docs = await db.execute(
        select(Documento).where(Documento.solicitud_id == solicitud_id)
    )
    documentos = result_docs.scalars().all()
    tipos = {d.tipo: d for d in documentos}

    if TipoDocumento.PENSUM_ORIGEN not in tipos:
        raise HTTPException(
            status_code=400,
            detail="Falta el certificado de notas del estudiante. "
                   "El estudiante debe subirlo en POST /documentos/{id}/notas"
        )

    if TipoDocumento.PENSUM_DESTINO not in tipos:
        raise HTTPException(
            status_code=400,
            detail="Falta el pensum del programa destino. "
                   "El coordinador debe subirlo en POST /documentos/{id}/pensum-destino"
        )

    # Cambiar estado a procesando
    historial = HistorialEstado(
        solicitud_id=solicitud.id,
        usuario_id=usuario.id,
        estado_anterior=solicitud.estado,
        estado_nuevo=EstadoSolicitud.PROCESANDO_IA,
    )
    solicitud.estado = EstadoSolicitud.PROCESANDO_IA
    db.add(historial)
    await db.commit()

    # Llamar a la IA
    try:
        resultado = await procesar_homologacion(
            ruta_origen=tipos[TipoDocumento.PENSUM_ORIGEN].ruta,
            ruta_destino=tipos[TipoDocumento.PENSUM_DESTINO].ruta,
        )
    except Exception as e:
        # Revertir estado si la IA falla
        solicitud.estado = EstadoSolicitud.EN_REVISION
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Error al procesar con IA: {str(e)}")

    # Guardar homologación
    homologacion = Homologacion(
        solicitud_id=solicitud.id,
        resumen_ia=resultado["resumen"],
        tokens_utilizados=resultado["tokens_utilizados"],
    )
    db.add(homologacion)
    await db.flush()

    for item in resultado["asignaturas"]:
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
            estado=EstadoAsignatura(item["estado"].lower()),
            justificacion=item.get("justificacion"),
            similitud_porcentaje=item.get("similitud_porcentaje"),
        ))

    # Pasar a pendiente rector
    historial2 = HistorialEstado(
        solicitud_id=solicitud.id,
        usuario_id=usuario.id,
        estado_anterior=EstadoSolicitud.PROCESANDO_IA,
        estado_nuevo=EstadoSolicitud.PENDIENTE_RECTOR,
    )
    solicitud.estado = EstadoSolicitud.PENDIENTE_RECTOR
    db.add(historial2)
    await db.commit()

    # Publicar evento Kafka con datos del estudiante para el email
    estudiante = solicitud.estudiante
    publicar_homologacion_completada(
        solicitud_id=str(solicitud.id),
        homologacion_id=str(homologacion.id),
        tokens=resultado["tokens_utilizados"],
    )

    # Recargar con asignaturas
    result_final = await db.execute(
        select(Homologacion)
        .where(Homologacion.id == homologacion.id)
        .options(selectinload(Homologacion.asignaturas))
    )
    return result_final.scalar_one()


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
    description="El rector descarga la resolución de homologación en formato Word (.docx).",
    responses={
        200: {"description": "Archivo Word generado"},
        404: {"description": "Homologación no encontrada"},
        403: {"description": "Solo el rector puede generar la resolución"},
    },
)
async def generar_resolucion(
    solicitud_id: UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol(Rol.RECTOR)),
):
    result = await db.execute(
        select(Homologacion)
        .where(Homologacion.solicitud_id == solicitud_id)
        .options(selectinload(Homologacion.asignaturas))
    )
    homologacion = result.scalar_one_or_none()

    if not homologacion:
        raise HTTPException(status_code=404, detail="Homologación no encontrada")

    result_sol = await db.execute(
        select(Solicitud)
        .where(Solicitud.id == solicitud_id)
        .options(selectinload(Solicitud.estudiante))
    )
    solicitud = result_sol.scalar_one_or_none()

    ruta = generar_resolucion_docx(homologacion, solicitud)

    return FileResponse(
        path=ruta,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"resolucion_homologacion_{solicitud_id}.docx",
    )