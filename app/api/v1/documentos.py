import uuid as uuid_module
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from uuid import UUID

from app.core.database import get_db
from app.core.deps import get_current_user, require_rol
from app.core.config import settings
from app.models.usuario import Usuario, Rol
from app.models.solicitud import Solicitud, EstadoSolicitud
from app.models.documento import Documento, TipoDocumento
from app.schemas.documento import DocumentoResponse
from app.services import storage_service

router = APIRouter(prefix="/documentos", tags=["Documentos"])

MIME_PDF = "application/pdf"
MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
LIMITE_PENSUM_ORIGEN = 4


def _generar_url_documento(solicitud_id: UUID, documento_id: UUID) -> str:
    return f"{settings.BASE_URL}/api/v1/documentos/{solicitud_id}/{documento_id}/descargar"


def _validar_pdf(file: UploadFile) -> None:
    if file.content_type != MIME_PDF:
        raise HTTPException(
            status_code=400,
            detail=f"Solo se aceptan archivos PDF. El archivo enviado tiene tipo: {file.content_type}",
        )


def _validar_pdf_o_docx(file: UploadFile) -> None:
    if file.content_type not in (MIME_PDF, MIME_DOCX):
        raise HTTPException(
            status_code=400,
            detail="Solo se aceptan archivos PDF o Word (.docx).",
        )


async def _leer_y_validar(file: UploadFile) -> bytes:
    contenido = await file.read()
    if len(contenido) == 0:
        raise HTTPException(status_code=400, detail="El archivo está vacío")
    if len(contenido) > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail=f"El archivo supera el límite de {settings.MAX_FILE_SIZE_MB} MB",
        )
    return contenido


async def _guardar_archivo(contenido: bytes, nombre_unico: str, content_type: str = "application/pdf") -> str:
    return await storage_service.subir(contenido, nombre_unico, content_type)


async def _obtener_solicitud(solicitud_id: UUID, db: AsyncSession) -> Solicitud:
    result = await db.execute(select(Solicitud).where(Solicitud.id == solicitud_id))
    solicitud = result.scalar_one_or_none()
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    return solicitud


async def _verificar_scope(solicitud: Solicitud, usuario: Usuario) -> None:
    if usuario.rol == Rol.ESTUDIANTE and solicitud.estudiante_id != usuario.id:
        raise HTTPException(status_code=403, detail="Sin permisos sobre esta solicitud")


async def _upsert_documento(
    db: AsyncSession,
    solicitud_id: UUID,
    tipo: TipoDocumento,
    file: UploadFile,
    mime: str = MIME_PDF,
) -> Documento:
    ext = ".docx" if mime == MIME_DOCX else ".pdf"
    contenido = await _leer_y_validar(file)
    nombre_unico = f"{solicitud_id}_{tipo.value}{ext}"
    ruta = await _guardar_archivo(contenido, nombre_unico, mime)

    result = await db.execute(
        select(Documento).where(
            Documento.solicitud_id == solicitud_id,
            Documento.tipo == tipo,
        )
    )
    doc = result.scalar_one_or_none()

    if doc:
        doc.nombre_original = file.filename
        doc.ruta = ruta
        doc.mime_type = mime
        doc.tamano_bytes = len(contenido)
    else:
        doc = Documento(
            solicitud_id=solicitud_id,
            tipo=tipo,
            nombre_original=file.filename,
            ruta=ruta,
            mime_type=mime,
            tamano_bytes=len(contenido),
        )
        db.add(doc)

    await db.commit()
    await db.refresh(doc)
    return doc


def _documento_a_response(doc: Documento) -> DocumentoResponse:
    return DocumentoResponse(
        id=doc.id,
        solicitud_id=doc.solicitud_id,
        tipo=doc.tipo,
        nombre_original=doc.nombre_original,
        mime_type=doc.mime_type,
        tamano_bytes=doc.tamano_bytes,
        url=_generar_url_documento(doc.solicitud_id, doc.id),
        creado_en=doc.creado_en,
    )


@router.post(
    "/{solicitud_id}/notas",
    response_model=DocumentoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Subir certificado de notas (Estudiante)",
    description=(
        "El estudiante sube su certificado oficial de calificaciones en PDF. "
        "Se permiten hasta 4 documentos distintos por solicitud. "
        "Cada subida crea un documento nuevo (no reemplaza el anterior). "
        "Solo disponible en estados: BORRADOR, ENVIADA, EN_REVISION."
    ),
    responses={
        201: {"description": "Certificado de notas subido"},
        400: {"description": "No es PDF, vacío, excede tamaño, estado incorrecto o límite alcanzado"},
        403: {"description": "Solo el dueño de la solicitud puede subir este documento"},
        404: {"description": "Solicitud no encontrada"},
    },
)
async def subir_notas_estudiante(
    solicitud_id: UUID,
    file: UploadFile = File(..., description="Certificado de calificaciones en PDF"),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol(Rol.ESTUDIANTE)),
):
    _validar_pdf(file)
    solicitud = await _obtener_solicitud(solicitud_id, db)

    if solicitud.estudiante_id != usuario.id:
        raise HTTPException(status_code=403, detail="Sin permisos sobre esta solicitud")

    estados_permitidos = [
        EstadoSolicitud.BORRADOR,
        EstadoSolicitud.ENVIADA,
        EstadoSolicitud.EN_REVISION,
    ]
    if solicitud.estado not in estados_permitidos:
        raise HTTPException(
            status_code=400,
            detail=f"No se pueden subir documentos en estado '{solicitud.estado.value}'",
        )

    count_result = await db.execute(
        select(func.count(Documento.id)).where(
            Documento.solicitud_id == solicitud_id,
            Documento.tipo == TipoDocumento.PENSUM_ORIGEN,
        )
    )
    count = count_result.scalar_one()
    if count >= LIMITE_PENSUM_ORIGEN:
        raise HTTPException(
            status_code=400,
            detail=f"Límite de {LIMITE_PENSUM_ORIGEN} documentos alcanzado. "
                   "Elimina uno antes de subir otro.",
        )

    contenido = await _leer_y_validar(file)
    sufijo = uuid_module.uuid4().hex
    nombre_unico = f"{solicitud_id}_pensum_origen_{sufijo}.pdf"
    ruta = await _guardar_archivo(contenido, nombre_unico)

    doc = Documento(
        solicitud_id=solicitud_id,
        tipo=TipoDocumento.PENSUM_ORIGEN,
        nombre_original=file.filename,
        ruta=ruta,
        mime_type=MIME_PDF,
        tamano_bytes=len(contenido),
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return _documento_a_response(doc)


@router.delete(
    "/{solicitud_id}/{documento_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar documento (Estudiante)",
    description=(
        "El estudiante elimina uno de sus documentos de notas. "
        "Solo permitido en estados BORRADOR, ENVIADA, EN_REVISION."
    ),
    responses={
        204: {"description": "Documento eliminado"},
        400: {"description": "Estado de solicitud no permite eliminar documentos"},
        403: {"description": "Sin permisos sobre este documento"},
        404: {"description": "Solicitud o documento no encontrado"},
    },
)
async def eliminar_documento(
    solicitud_id: UUID,
    documento_id: UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol(Rol.ESTUDIANTE)),
):
    solicitud = await _obtener_solicitud(solicitud_id, db)

    if solicitud.estudiante_id != usuario.id:
        raise HTTPException(status_code=403, detail="Sin permisos sobre esta solicitud")

    estados_permitidos = [
        EstadoSolicitud.BORRADOR,
        EstadoSolicitud.ENVIADA,
        EstadoSolicitud.EN_REVISION,
    ]
    if solicitud.estado not in estados_permitidos:
        raise HTTPException(
            status_code=400,
            detail=f"No se pueden eliminar documentos en estado '{solicitud.estado.value}'",
        )

    result = await db.execute(
        select(Documento).where(
            Documento.id == documento_id,
            Documento.solicitud_id == solicitud_id,
        )
    )
    documento = result.scalar_one_or_none()
    if not documento:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    await storage_service.eliminar(documento.ruta)
    await db.delete(documento)
    await db.commit()


@router.post(
    "/{solicitud_id}/pensum-destino",
    response_model=DocumentoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Subir pensum destino (Coordinador)",
    description=(
        "El coordinador sube el plan de estudios del programa destino en PDF. "
        "Disponible en estados: EN_REVISION o REVISION_COORDINADOR (para reprocesar)."
    ),
    responses={
        201: {"description": "Pensum destino subido"},
        400: {"description": "No es PDF, vacío, excede tamaño o estado no permitido"},
        403: {"description": "Solo coordinadores pueden subir el pensum destino"},
        404: {"description": "Solicitud no encontrada"},
    },
)
async def subir_pensum_destino(
    solicitud_id: UUID,
    file: UploadFile = File(..., description="Plan de estudios del programa destino en PDF"),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol(Rol.COORDINADOR)),
):
    _validar_pdf(file)
    solicitud = await _obtener_solicitud(solicitud_id, db)

    estados_permitidos = [EstadoSolicitud.EN_REVISION, EstadoSolicitud.REVISION_COORDINADOR]
    if solicitud.estado not in estados_permitidos:
        raise HTTPException(
            status_code=400,
            detail="El pensum destino solo se puede subir cuando la solicitud está EN_REVISION o REVISION_COORDINADOR",
        )

    doc = await _upsert_documento(db, solicitud_id, TipoDocumento.PENSUM_DESTINO, file)
    return _documento_a_response(doc)


@router.post(
    "/{solicitud_id}/resolucion",
    response_model=DocumentoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Subir resolución editada (Coordinador/Rector)",
    description=(
        "Sube o reemplaza la resolución de homologación en PDF o Word (.docx). "
        "Coordinador: permitido en REVISION_COORDINADOR. "
        "Rector: permitido en PENDIENTE_RECTOR. "
        "Ambos: permitido en APROBADA."
    ),
    responses={
        201: {"description": "Resolución subida"},
        400: {"description": "Tipo de archivo no permitido, estado incorrecto o sin permisos para este estado"},
        403: {"description": "Solo coordinadores y rectores pueden subir resoluciones"},
        404: {"description": "Solicitud no encontrada"},
    },
)
async def subir_resolucion(
    solicitud_id: UUID,
    file: UploadFile = File(..., description="Resolución en PDF o Word (.docx)"),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol(Rol.COORDINADOR, Rol.VICERRECTOR)),
):
    _validar_pdf_o_docx(file)
    solicitud = await _obtener_solicitud(solicitud_id, db)

    estado = solicitud.estado
    rol = usuario.rol

    estados_coordinador = {EstadoSolicitud.REVISION_COORDINADOR, EstadoSolicitud.APROBADA}
    estados_rector = {EstadoSolicitud.PENDIENTE_RECTOR, EstadoSolicitud.APROBADA}

    if rol == Rol.COORDINADOR and estado not in estados_coordinador:
        raise HTTPException(
            status_code=400,
            detail="El coordinador solo puede subir la resolución en estados REVISION_COORDINADOR o APROBADA",
        )
    if rol == Rol.VICERRECTOR and estado not in estados_rector:
        raise HTTPException(
            status_code=400,
            detail="El rector solo puede subir la resolución en estados PENDIENTE_RECTOR o APROBADA",
        )

    mime = file.content_type
    doc = await _upsert_documento(db, solicitud_id, TipoDocumento.RESOLUCION, file, mime=mime)
    return _documento_a_response(doc)


@router.get(
    "/{solicitud_id}",
    response_model=list[DocumentoResponse],
    summary="Listar documentos de una solicitud",
    description=(
        "Retorna los documentos subidos para una solicitud con sus URLs públicas. "
        "El estudiante solo ve los de sus propias solicitudes."
    ),
    responses={
        404: {"description": "Solicitud no encontrada"},
        403: {"description": "Sin permisos"},
    },
)
async def listar_documentos(
    solicitud_id: UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    solicitud = await _obtener_solicitud(solicitud_id, db)
    await _verificar_scope(solicitud, usuario)

    query = select(Documento).where(Documento.solicitud_id == solicitud_id)
    if usuario.rol == Rol.ESTUDIANTE:
        query = query.where(Documento.tipo != TipoDocumento.RESOLUCION)

    result = await db.execute(query)
    documentos = result.scalars().all()
    return [_documento_a_response(doc) for doc in documentos]


@router.get(
    "/{solicitud_id}/{documento_id}/descargar",
    summary="Descargar documento",
    description=(
        "Descarga el archivo de un documento específico. "
        "El estudiante solo puede descargar documentos de sus propias solicitudes."
    ),
    responses={
        200: {"description": "Archivo descargado"},
        404: {"description": "Documento no encontrado o archivo no existe en disco"},
        403: {"description": "Sin permisos"},
    },
)
async def descargar_documento(
    solicitud_id: UUID,
    documento_id: UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    solicitud = await _obtener_solicitud(solicitud_id, db)
    await _verificar_scope(solicitud, usuario)

    result = await db.execute(
        select(Documento).where(
            Documento.id == documento_id,
            Documento.solicitud_id == solicitud_id,
        )
    )
    documento = result.scalar_one_or_none()

    if not documento:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    if usuario.rol == Rol.ESTUDIANTE and documento.tipo == TipoDocumento.RESOLUCION:
        raise HTTPException(status_code=403, detail="No tienes permiso para descargar este documento")

    try:
        contenido = await storage_service.descargar(documento.ruta)
    except Exception:
        raise HTTPException(
            status_code=404,
            detail="El archivo no existe en el servidor. Contacta al administrador.",
        )

    return Response(
        content=contenido,
        media_type=documento.mime_type,
        headers={"Content-Disposition": f'attachment; filename="{documento.nombre_original}"'},
    )
