import os
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
from uuid import UUID
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.deps import get_current_user, require_rol
from app.models.usuario import Usuario, Rol
from app.models.solicitud import Solicitud, EstadoSolicitud, HistorialEstado
from app.models.documento import Documento, TipoDocumento
from app.models.homologacion import Homologacion, HomologacionAsignatura, EstadoAsignatura
from app.models.academico import Asignatura
from app.schemas.homologacion import (
    HomologacionResponse,
    HomologacionAsignaturaResponse,
    ActualizarAsignaturaRequest,
    AgregarAsignaturaRequest,
)
import asyncio
from app.services.ai_service import procesar_homologacion
from app.services.doc_service import generar_resolucion_docx
from app.services.email_service import notificar_homologacion_completada
from app.services import storage_service

router = APIRouter(prefix="/homologaciones", tags=["Homologaciones"])


def _build_pensum_text(asignaturas: list, programa_nombre: str = "") -> str:
    lines = [f"PLAN DE ESTUDIOS — {programa_nombre.upper()}\n"]
    sem_actual = None
    for a in sorted(asignaturas, key=lambda x: (x.semestre or 0, x.nombre)):
        if a.semestre != sem_actual:
            sem_actual = a.semestre
            lines.append(f"\nSEMESTRE {sem_actual}:")
        cr = a.creditos
        ih = a.intensidad_horaria or cr
        tipo = a.tipo or "T"
        cod = a.codigo or ""
        lines.append(f"  {cod} | {a.nombre} | CR:{cr} | IH:{ih} | Tipo:{tipo}")
    return "\n".join(lines)


@router.post(
    "/{solicitud_id}/procesar",
    response_model=HomologacionResponse,
    summary="Procesar homologación con IA",
    description=(
        "El coordinador activa el procesamiento con IA. "
        "Requiere que el estudiante haya subido sus notas. "
        "Si el programa destino tiene asignaturas en la BD, el pensum-destino PDF es opcional. "
        "La solicitud debe estar en estado EN_REVISION o REVISION_COORDINADOR."
    ),
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

    asignaturas_programa: list[Asignatura] = []
    if solicitud.programa_destino_id:
        result_asig = await db.execute(
            select(Asignatura)
            .where(Asignatura.programa_id == solicitud.programa_destino_id)
            .order_by(Asignatura.semestre, Asignatura.nombre)
        )
        asignaturas_programa = result_asig.scalars().all()

    if not docs_destino and not asignaturas_programa:
        raise HTTPException(
            status_code=400,
            detail="Falta el pensum del programa destino. "
                   "El coordinador debe subirlo en POST /documentos/{id}/pensum-destino, "
                   "o el programa debe tener asignaturas registradas en la base de datos.",
        )

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
        if asignaturas_programa:
            pensum_texto = _build_pensum_text(asignaturas_programa, solicitud.programa_destino or "")
            resultado = await procesar_homologacion(
                rutas_origen=[d.ruta for d in docs_origen],
                nombre_estudiante=nombre_estudiante,
                pensum_destino_texto=pensum_texto,
            )
        else:
            resultado = await procesar_homologacion(
                rutas_origen=[d.ruta for d in docs_origen],
                nombre_estudiante=nombre_estudiante,
                ruta_destino=docs_destino[0].ruta,
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
        .options(
            selectinload(Homologacion.asignaturas),
            selectinload(Homologacion.solicitud).selectinload(Solicitud.estudiante),
        )
    )
    return result_final.scalar_one()


@router.patch(
    "/{solicitud_id}/asignaturas/{asignatura_id}",
    response_model=HomologacionAsignaturaResponse,
    summary="Actualizar asignatura homologada",
    description="El coordinador puede modificar estado, justificación y datos de destino de una asignatura.",
)
async def actualizar_asignatura(
    solicitud_id: UUID,
    asignatura_id: UUID,
    body: ActualizarAsignaturaRequest,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol(Rol.COORDINADOR, Rol.VICERRECTOR)),
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

    if body.estado is not None:
        asignatura.estado = body.estado
        if asignatura.estado_ia_original is not None:
            asignatura.fue_corregida = (body.estado != asignatura.estado_ia_original)
    if body.justificacion is not None:
        asignatura.justificacion = body.justificacion
    if body.asignatura_destino is not None:
        asignatura.asignatura_destino = body.asignatura_destino
    if body.creditos_destino is not None:
        asignatura.creditos_destino = body.creditos_destino
    if body.codigo_destino is not None:
        asignatura.codigo_destino = body.codigo_destino
    if body.semestre_destino is not None:
        asignatura.semestre_destino = body.semestre_destino
    if body.intensidad_horaria_destino is not None:
        asignatura.intensidad_horaria_destino = body.intensidad_horaria_destino
    if body.tipo_destino is not None:
        asignatura.tipo_destino = body.tipo_destino
    if body.calificacion_origen is not None:
        asignatura.calificacion_origen = body.calificacion_origen

    await db.commit()
    await db.refresh(asignatura)
    return asignatura


@router.post(
    "/{solicitud_id}/asignaturas",
    response_model=HomologacionAsignaturaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Agregar asignatura manualmente",
    description="El coordinador puede agregar una asignatura adicional a la homologación.",
)
async def agregar_asignatura(
    solicitud_id: UUID,
    body: AgregarAsignaturaRequest,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol(Rol.COORDINADOR, Rol.VICERRECTOR)),
):
    result = await db.execute(
        select(Homologacion).where(Homologacion.solicitud_id == solicitud_id)
    )
    homologacion = result.scalar_one_or_none()
    if not homologacion:
        raise HTTPException(status_code=404, detail="Homologación no encontrada")

    nueva = HomologacionAsignatura(
        homologacion_id=homologacion.id,
        asignatura_origen=body.asignatura_origen,
        creditos_origen=body.creditos_origen,
        calificacion_origen=body.calificacion_origen,
        asignatura_destino=body.asignatura_destino,
        codigo_destino=body.codigo_destino,
        semestre_destino=body.semestre_destino,
        creditos_destino=body.creditos_destino,
        intensidad_horaria_destino=body.intensidad_horaria_destino,
        tipo_destino=body.tipo_destino,
        estado=body.estado,
        estado_ia_original=None,
        fue_corregida=False,
        justificacion=body.justificacion,
        similitud_porcentaje=body.similitud_porcentaje,
    )
    db.add(nueva)
    await db.commit()
    await db.refresh(nueva)
    return nueva


@router.delete(
    "/{solicitud_id}/asignaturas/{asignatura_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar asignatura",
    description="El coordinador puede eliminar una asignatura de la homologación.",
)
async def eliminar_asignatura(
    solicitud_id: UUID,
    asignatura_id: UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol(Rol.COORDINADOR, Rol.VICERRECTOR)),
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

    await db.delete(asignatura)
    await db.commit()


@router.post(
    "/{solicitud_id}/enviar-rector",
    status_code=status.HTTP_200_OK,
    summary="Enviar homologación al vicerrector",
    description=(
        "El coordinador envía la homologación revisada al vicerrector para su aprobación. "
        "La solicitud debe estar en estado REVISION_COORDINADOR."
    ),
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
            detail="La solicitud debe estar en estado REVISION_COORDINADOR para enviar al vicerrector",
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

    return {"mensaje": "Homologación enviada al vicerrector correctamente"}


@router.get(
    "/estadisticas-ia",
    summary="Estadísticas de precisión de la IA",
    description=(
        "Retorna métricas sobre qué tan seguido el coordinador corrige las decisiones de la IA. "
        "Solo para coordinadores y vicerrectores."
    ),
)
async def estadisticas_ia(
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_rol(Rol.COORDINADOR, Rol.VICERRECTOR)),
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
    "/{solicitud_id}/resumen",
    summary="Dashboard de homologación",
    description=(
        "Retorna el resumen generado por la IA junto con estadísticas detalladas de la homologación. "
        "Visible para coordinador y vicerrector. El estudiante puede verlo solo para sus propias solicitudes."
    ),
)
async def resumen_homologacion(
    solicitud_id: UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    result = await db.execute(
        select(Homologacion)
        .where(Homologacion.solicitud_id == solicitud_id)
        .options(
            selectinload(Homologacion.asignaturas),
            selectinload(Homologacion.solicitud).selectinload(Solicitud.estudiante),
        )
    )
    homologacion = result.scalar_one_or_none()
    if not homologacion:
        raise HTTPException(status_code=404, detail="Homologación no encontrada")

    if usuario.rol == Rol.ESTUDIANTE:
        sol = homologacion.solicitud
        if not sol or sol.estudiante_id != usuario.id:
            raise HTTPException(status_code=403, detail="Sin permisos sobre esta solicitud")
    elif usuario.rol not in (Rol.COORDINADOR, Rol.VICERRECTOR):
        raise HTTPException(status_code=403, detail="Sin permisos suficientes")

    asigs = homologacion.asignaturas
    conteo = {e.value: 0 for e in EstadoAsignatura}
    creditos = {e.value: 0 for e in EstadoAsignatura}
    total_creditos = 0

    for a in asigs:
        key = a.estado.value
        conteo[key] = conteo.get(key, 0) + 1
        cr = a.creditos_destino or 0
        creditos[key] = creditos.get(key, 0) + cr
        total_creditos += cr

    total_asigs = len(asigs)
    corregidas = sum(1 for a in asigs if a.fue_corregida)

    solicitud = homologacion.solicitud
    estudiante = getattr(solicitud, "estudiante", None) if solicitud else None

    return {
        "solicitud_id": str(solicitud_id),
        "resumen_ia": homologacion.resumen_ia,
        "tokens_utilizados": homologacion.tokens_utilizados,
        "estudiante": {
            "nombre": getattr(estudiante, "nombre", None),
            "apellido": getattr(estudiante, "apellido", None),
        } if estudiante else None,
        "estadisticas": {
            "total_asignaturas": total_asigs,
            "total_creditos_homologados": creditos.get("homologada", 0),
            "total_creditos_pendientes": creditos.get("pendiente", 0),
            "asignaturas_corregidas_por_coordinador": corregidas,
        },
        "por_estado": {
            estado: {"cantidad": conteo.get(estado, 0), "creditos": creditos.get(estado, 0)}
            for estado in [e.value for e in EstadoAsignatura]
        },
        "datos_grafica": [
            {"estado": estado, "cantidad": conteo.get(estado, 0)}
            for estado in [e.value for e in EstadoAsignatura]
            if conteo.get(estado, 0) > 0
        ],
    }


@router.get(
    "/{solicitud_id}",
    response_model=HomologacionResponse,
    summary="Obtener homologación",
    description="Retorna el resultado del análisis de homologación.",
)
async def obtener_homologacion(
    solicitud_id: UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol(Rol.COORDINADOR, Rol.VICERRECTOR)),
):
    result = await db.execute(
        select(Homologacion)
        .where(Homologacion.solicitud_id == solicitud_id)
        .options(
            selectinload(Homologacion.asignaturas),
            selectinload(Homologacion.solicitud).selectinload(Solicitud.estudiante),
        )
    )
    homologacion = result.scalar_one_or_none()

    if not homologacion:
        raise HTTPException(status_code=404, detail="Homologación no encontrada")

    return homologacion


@router.post(
    "/{solicitud_id}/generar-resolucion",
    summary="Generar resolución Word",
    description=(
        "Descarga la resolución de homologación en formato Word (.docx). "
        "Exclusivo para coordinador, vicerrector y admin. El estudiante no tiene acceso."
    ),
)
async def generar_resolucion(
    solicitud_id: UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol(Rol.COORDINADOR, Rol.VICERRECTOR, Rol.ADMIN)),
):
    result_sol = await db.execute(
        select(Solicitud)
        .where(Solicitud.id == solicitud_id)
        .options(selectinload(Solicitud.estudiante))
    )
    solicitud = result_sol.scalar_one_or_none()

    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    if usuario.rol == Rol.COORDINADOR:
        estados_permitidos = {
            EstadoSolicitud.REVISION_COORDINADOR,
            EstadoSolicitud.PENDIENTE_RECTOR,
            EstadoSolicitud.APROBADA,
        }
        if solicitud.estado not in estados_permitidos:
            raise HTTPException(
                status_code=400,
                detail="La resolución solo está disponible en estados REVISION_COORDINADOR, PENDIENTE_RECTOR o APROBADA",
            )
    elif usuario.rol == Rol.VICERRECTOR:
        estados_permitidos = {EstadoSolicitud.PENDIENTE_RECTOR, EstadoSolicitud.APROBADA}
        if solicitud.estado not in estados_permitidos:
            raise HTTPException(
                status_code=400,
                detail="La resolución solo está disponible en estados PENDIENTE_RECTOR o APROBADA",
            )

    result = await db.execute(
        select(Homologacion)
        .where(Homologacion.solicitud_id == solicitud_id)
        .options(selectinload(Homologacion.asignaturas))
    )
    homologacion = result.scalar_one_or_none()

    if not homologacion:
        raise HTTPException(status_code=404, detail="Homologación no encontrada")

    asignaturas_destino: list[Asignatura] = []
    if solicitud.programa_destino_id:
        result_asig = await db.execute(
            select(Asignatura)
            .where(Asignatura.programa_id == solicitud.programa_destino_id)
            .order_by(Asignatura.semestre, Asignatura.nombre)
        )
        asignaturas_destino = result_asig.scalars().all()

    ruta = generar_resolucion_docx(homologacion, solicitud, asignaturas_destino)

    with open(ruta, "rb") as f:
        contenido = f.read()

    return Response(
        content=contenido,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f'attachment; filename="resolucion_homologacion_{solicitud_id}.docx"'
        },
    )
