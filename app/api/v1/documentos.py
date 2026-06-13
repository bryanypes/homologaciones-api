import os
import uuid
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

router = APIRouter(prefix="/documentos", tags=["Documentos"])

ALLOWED_MIME = "application/pdf"


def validar_pdf(file: UploadFile) -> None:
    if file.content_type != ALLOWED_MIME:
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos PDF")


async def guardar_archivo(file: UploadFile, solicitud_id: UUID, tipo: TipoDocumento) -> tuple[str, int]:
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    nombre_unico = f"{solicitud_id}_{tipo.value}.pdf"
    ruta = os.path.join(settings.UPLOAD_DIR, nombre_unico)

    contenido = await file.read()
    tamano = len(contenido)

    if tamano > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail=f"El archivo supera el límite de {settings.MAX_FILE_SIZE_MB}MB",
        )
    if tamano == 0:
        raise HTTPException(status_code=400, detail="El archivo está vacío")

    with open(ruta, "wb") as f:
        f.write(contenido)

    return ruta, tamano


async def _obtener_solicitud_con_permiso(
    solicitud_id: UUID, usuario: Usuario, db: AsyncSession
) -> Solicitud:
    result = await db.execute(select(Solicitud).where(Solicitud.id == solicitud_id))
    solicitud = result.scalar_one_or_none()
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if usuario.rol == Rol.ESTUDIANTE and solicitud.estudiante_id != usuario.id:
        raise HTTPException(status_code=403, detail="Sin permisos")
    return solicitud


async def _subir_documento(
    solicitud_id: UUID,
    file: UploadFile,
    tipo: TipoDocumento,
    db: AsyncSession,
    usuario: Usuario,
) -> Documento:
    validar_pdf(file)

    result = await db.execute(select(Solicitud).where(Solicitud.id == solicitud_id))
    solicitud = result.scalar_one_or_none()

    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if solicitud.estudiante_id != usuario.id:
        raise HTTPException(status_code=403, detail="Sin permisos")
    if solicitud.estado not in [
        EstadoSolicitud.BORRADOR,
        EstadoSolicitud.ENVIADA,
        EstadoSolicitud.EN_REVISION,
    ]:
        raise HTTPException(status_code=400, detail="No se pueden subir documentos en este estado")

    ruta, tamano = await guardar_archivo(file, solicitud_id, tipo)

    result_doc = await db.execute(
        select(Documento).where(
            Documento.solicitud_id == solicitud_id,
            Documento.tipo == tipo,
        )
    )
    doc_existente = result_doc.scalar_one_or_none()

    if doc_existente:
        doc_existente.nombre_original = file.filename
        doc_existente.ruta = ruta
        doc_existente.tamano_bytes = tamano
        await db.commit()
        await db.refresh(doc_existente)
        return doc_existente

    documento = Documento(
        solicitud_id=solicitud_id,
        tipo=tipo,
        nombre_original=file.filename,
        ruta=ruta,
        mime_type=ALLOWED_MIME,
        tamano_bytes=tamano,
    )
    db.add(documento)
    await db.commit()
    await db.refresh(documento)
    return documento


@router.post(
    "/{solicitud_id}/pensum-origen",
    status_code=status.HTTP_201_CREATED,
    summary="Subir pensum de origen",
    description="El estudiante sube el PDF del pensum de la institución de origen.",
    responses={
        201: {"description": "Documento subido"},
        400: {"description": "No es PDF, archivo vacío o tamaño excedido"},
        403: {"description": "Solo el dueño de la solicitud puede subir documentos"},
    },
)
async def subir_pensum_origen(
    solicitud_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol(Rol.ESTUDIANTE)),
):
    return await _subir_documento(solicitud_id, file, TipoDocumento.PENSUM_ORIGEN, db, usuario)


@router.post(
    "/{solicitud_id}/pensum-destino",
    status_code=status.HTTP_201_CREATED,
    summary="Subir pensum de destino",
    description="El estudiante sube el PDF del pensum de la institución de destino.",
    responses={
        201: {"description": "Documento subido"},
        400: {"description": "No es PDF, archivo vacío o tamaño excedido"},
        403: {"description": "Solo el dueño de la solicitud puede subir documentos"},
    },
)
async def subir_pensum_destino(
    solicitud_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol(Rol.ESTUDIANTE)),
):
    return await _subir_documento(solicitud_id, file, TipoDocumento.PENSUM_DESTINO, db, usuario)


@router.get(
    "/{solicitud_id}",
    summary="Listar documentos",
    description="Lista los documentos de una solicitud. El estudiante solo ve los suyos.",
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
    await _obtener_solicitud_con_permiso(solicitud_id, usuario, db)

    result_docs = await db.execute(
        select(Documento).where(Documento.solicitud_id == solicitud_id)
    )
    return result_docs.scalars().all()


@router.get(
    "/{solicitud_id}/{documento_id}/descargar",
    summary="Descargar PDF",
    description=(
        "Descarga el PDF de un documento específico. "
        "El estudiante solo puede descargar documentos de sus propias solicitudes."
    ),
    responses={
        200: {"description": "Archivo PDF"},
        404: {"description": "Documento no encontrado"},
        403: {"description": "Sin permisos"},
    },
)
async def descargar_documento(
    solicitud_id: UUID,
    documento_id: UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    await _obtener_solicitud_con_permiso(solicitud_id, usuario, db)

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
        raise HTTPException(status_code=404, detail="Archivo no encontrado en el servidor")

    return FileResponse(
        path=documento.ruta,
        media_type="application/pdf",
        filename=documento.nombre_original,
    )