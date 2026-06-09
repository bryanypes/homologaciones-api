import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from app.core.database import get_db
from app.core.deps import get_current_user, require_rol
from app.core.config import settings
from app.models.usuario import Usuario, Rol
from app.models.solicitud import Solicitud, EstadoSolicitud
from app.models.documento import Documento, TipoDocumento
from app.schemas import solicitud

router = APIRouter(prefix="/documentos", tags=["documentos"])

ALLOWED_MIME = "application/pdf"


def validar_pdf(file: UploadFile):
    if file.content_type != ALLOWED_MIME:
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos PDF")


async def guardar_archivo(file: UploadFile, solicitud_id: UUID, tipo: TipoDocumento) -> tuple[str, int]:
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    extension = ".pdf"
    nombre_unico = f"{solicitud_id}_{tipo.value}{extension}"
    ruta = os.path.join(settings.UPLOAD_DIR, nombre_unico)

    contenido = await file.read()
    tamano = len(contenido)

    if tamano > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"El archivo supera el límite de {settings.MAX_FILE_SIZE_MB}MB")

    if tamano == 0:
        raise HTTPException(status_code=400, detail="El archivo está vacío")

    with open(ruta, "wb") as f:
        f.write(contenido)

    return ruta, tamano


@router.post("/{solicitud_id}/pensum-origen", status_code=status.HTTP_201_CREATED)
async def subir_pensum_origen(
    solicitud_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol(Rol.ESTUDIANTE)),
):
    validar_pdf(file)

    result = await db.execute(select(Solicitud).where(Solicitud.id == solicitud_id))
    solicitud = result.scalar_one_or_none()

    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    if solicitud.estudiante_id != usuario.id:
        raise HTTPException(status_code=403, detail="Sin permisos")

    if solicitud.estado not in [EstadoSolicitud.BORRADOR, EstadoSolicitud.ENVIADA, EstadoSolicitud.EN_REVISION]:
        raise HTTPException(status_code=400, detail="No se pueden subir documentos en este estado")

    ruta, tamano = await guardar_archivo(file, solicitud_id, TipoDocumento.PENSUM_ORIGEN)

    result_doc = await db.execute(
        select(Documento).where(
            Documento.solicitud_id == solicitud_id,
            Documento.tipo == TipoDocumento.PENSUM_ORIGEN,
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
        tipo=TipoDocumento.PENSUM_ORIGEN,
        nombre_original=file.filename,
        ruta=ruta,
        mime_type=ALLOWED_MIME,
        tamano_bytes=tamano,
    )
    db.add(documento)
    await db.commit()
    await db.refresh(documento)
    return documento


@router.post("/{solicitud_id}/pensum-destino", status_code=status.HTTP_201_CREATED)
async def subir_pensum_destino(
    solicitud_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_rol(Rol.ESTUDIANTE)),
):
    validar_pdf(file)

    result = await db.execute(select(Solicitud).where(Solicitud.id == solicitud_id))
    solicitud = result.scalar_one_or_none()

    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    if solicitud.estudiante_id != usuario.id:
        raise HTTPException(status_code=403, detail="Sin permisos")

    if solicitud.estado not in [EstadoSolicitud.BORRADOR, EstadoSolicitud.ENVIADA, EstadoSolicitud.EN_REVISION]:
        raise HTTPException(status_code=400, detail="No se pueden subir documentos en este estado")

    ruta, tamano = await guardar_archivo(file, solicitud_id, TipoDocumento.PENSUM_DESTINO)

    result_doc = await db.execute(
        select(Documento).where(
            Documento.solicitud_id == solicitud_id,
            Documento.tipo == TipoDocumento.PENSUM_DESTINO,
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
        tipo=TipoDocumento.PENSUM_DESTINO,
        nombre_original=file.filename,
        ruta=ruta,
        mime_type=ALLOWED_MIME,
        tamano_bytes=tamano,
    )
    db.add(documento)
    await db.commit()
    await db.refresh(documento)
    return documento


@router.get("/{solicitud_id}", )
async def listar_documentos(
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

    result_docs = await db.execute(
        select(Documento).where(Documento.solicitud_id == solicitud_id)
    )
    return result_docs.scalars().all()