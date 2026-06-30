import os
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

from app.core.database import get_db
from app.core.deps import get_current_user, require_rol
from app.core.config import settings
from app.models.usuario import Usuario, Rol
from app.models.solicitud import Solicitud, EstadoSolicitud
from app.models.documento import Documento, TipoDocumento
from app.schemas.documento import DocumentoResponse

router = APIRouter(prefix="/documentos", tags=["Documentos"])

ALLOWED_MIME = "application/pdf"


# ──────────────────────────────────────────────────────────────────────────────
# Helpers internos
# ──────────────────────────────────────────────────────────────────────────────

def _generar_url_documento(solicitud_id: UUID, documento_id: UUID) -> str:
    """Genera la URL pública para descargar un documento"""
    return f"{settings.BASE_URL}/api/v1/documentos/{solicitud_id}/{documento_id}/descargar"


def _validar_pdf(file: UploadFile) -> None:
    if file.content_type != ALLOWED_MIME:
        raise HTTPException(
            status_code=400,
            detail="Solo se aceptan archivos PDF. El archivo enviado tiene tipo: "
                   f"{file.content_type}",
        )


async def _guardar_archivo(
    file: UploadFile, solicitud_id: UUID, tipo: TipoDocumento
) -> tuple[str, int]:
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    nombre_unico = f"{solicitud_id}_{tipo.value}.pdf"
    ruta = os.path.join(settings.UPLOAD_DIR, nombre_unico)

    contenido = await file.read()
    tamano = len(contenido)

    if tamano == 0:
        raise HTTPException(status_code=400, detail="El archivo está vacío")

    if tamano > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail=f"El archivo supera el límite de {settings.MAX_FILE_SIZE_MB} MB",
        )

    with open(ruta, "wb") as f:
        f.write(contenido)

    return ruta, tamano


async def _obtener_solicitud(
    solicitud_id: UUID, db: AsyncSession
) -> Solicitud:
    result = await db.execute(
        select(Solicitud).where(Solicitud.id == solicitud_id)
    )
    solicitud = result.scalar_one_or_none()
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    return solicitud


async def _verificar_scope(
    solicitud: Solicitud, usuario: Usuario
) -> None:
    """Estudiante solo puede ver/tocar sus propias solicitudes."""
    if usuario.rol == Rol.ESTUDIANTE and solicitud.estudiante_id != usuario.id:
        raise HTTPException(status_code=403, detail="Sin permisos sobre esta solicitud")


async def _upsert_documento(
    db: AsyncSession,
    solicitud_id: UUID,
    tipo: TipoDocumento,
    file: UploadFile,
) -> Documento:
    """Crea o reemplaza el documento de un tipo dado para una solicitud."""
    ruta, tamano = await _guardar_archivo(file, solicitud_id, tipo)

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
        doc.tamano_bytes = tamano
    else:
        doc = Documento(
            solicitud_id=solicitud_id,
            tipo=tipo,
            nombre_original=file.filename,
            ruta=ruta,
            mime_type=ALLOWED_MIME,
            tamano_bytes=tamano,
        )
        db.add(doc)

    await db.commit()
    await db.refresh(doc)
    return doc


def _documento_a_response(doc: Documento) -> DocumentoResponse:
    """Convierte un modelo Documento a DocumentoResponse con URL"""
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


# ──────────────────────────────────────────────────────────────────────────────
# Endpoints — Estudiante
# ──────────────────────────────────────────────────────────────────────────────

@router.post(
    "/{solicitud_id}/notas",
    response_model=DocumentoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Subir certificado de notas (Estudiante)",
    description=(
        "El estudiante sube su certificado oficial de calificaciones o hoja de vida "
        "académica en PDF. Este documento es el **pensum de origen** que la IA analizará. "
        "Puede resubirse para reemplazar el anterior. "
        "Solo disponible en estados: BORRADOR, ENVIADA, EN_REVISION."
    ),
    responses={
        201: {"description": "Certificado de notas subido"},
        400: {"description": "No es PDF, vacío, excede tamaño o estado incorrecto"},
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
            detail=f"No se pueden subir documentos en estado '{solicitud.estado.value}'"
        )

    doc = await _upsert_documento(db, solicitud_id, TipoDocumento.PENSUM_ORIGEN, file)
    return _documento_a_response(doc)


# ──────────────────────────────────────────────────────────────────────────────
# Endpoints — Coordinador
# ──────────────────────────────────────────────────────────────────────────────

@router.post(
    "/{solicitud_id}/pensum-destino",
    response_model=DocumentoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Subir pensum destino (Coordinador)",
    description=(
        "El coordinador sube el plan de estudios (pensum) del programa al que el "
        "estudiante desea trasladarse. Este PDF es el que la IA usará como referencia "
        "para determinar equivalencias. "
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


# ──────────────────────────────────────────────────────────────────────────────
# Endpoints — Lectura (todos los roles con scope)
# ──────────────────────────────────────────────────────────────────────────────

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

    result = await db.execute(
        select(Documento).where(Documento.solicitud_id == solicitud_id)
    )
    documentos = result.scalars().all()
    
    return [_documento_a_response(doc) for doc in documentos]


@router.get(
    "/{solicitud_id}/{documento_id}/descargar",
    summary="Descargar PDF",
    description=(
        "Descarga el PDF de un documento específico. "
        "El estudiante solo puede descargar documentos de sus propias solicitudes."
    ),
    responses={
        200: {"description": "Archivo PDF"},
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

    if not os.path.exists(documento.ruta):
        raise HTTPException(
            status_code=404,
            detail="El archivo no existe en el servidor. Contacta al administrador."
        )

    return FileResponse(
        path=documento.ruta,
        media_type="application/pdf",
        filename=documento.nombre_original,
    )