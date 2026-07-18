import asyncio
import logging
import os
import tempfile

from app.core.config import settings

logger = logging.getLogger(__name__)


def _r2_habilitado() -> bool:
    return all([
        settings.R2_ACCOUNT_ID,
        settings.R2_ACCESS_KEY_ID,
        settings.R2_SECRET_ACCESS_KEY,
        settings.R2_BUCKET_NAME,
    ])


def _cliente_r2():
    import boto3
    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        region_name="auto",
    )


async def subir(contenido: bytes, key: str, content_type: str = "application/pdf") -> str:
    if _r2_habilitado():
        def _upload():
            _cliente_r2().put_object(
                Bucket=settings.R2_BUCKET_NAME,
                Key=key,
                Body=contenido,
                ContentType=content_type,
            )
        await asyncio.to_thread(_upload)
        logger.info("[Storage] Subido a R2: %s (%d bytes)", key, len(contenido))
    else:
        ruta = os.path.join(settings.UPLOAD_DIR, key)
        def _write():
            os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
            with open(ruta, "wb") as f:
                f.write(contenido)
        await asyncio.to_thread(_write)
        logger.info("[Storage] Guardado en disco: %s", ruta)
    return key


async def descargar(key: str) -> bytes:
    if _r2_habilitado():
        def _download():
            resp = _cliente_r2().get_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
            return resp["Body"].read()
        contenido = await asyncio.to_thread(_download)
        logger.info("[Storage] Descargado de R2: %s (%d bytes)", key, len(contenido))
        return contenido
    else:
        ruta = os.path.join(settings.UPLOAD_DIR, key)
        def _read():
            with open(ruta, "rb") as f:
                return f.read()
        return await asyncio.to_thread(_read)


async def eliminar(key: str) -> None:
    if _r2_habilitado():
        def _delete():
            _cliente_r2().delete_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
        await asyncio.to_thread(_delete)
        logger.info("[Storage] Eliminado de R2: %s", key)
    else:
        ruta = os.path.join(settings.UPLOAD_DIR, key)
        try:
            os.remove(ruta)
        except OSError:
            pass


async def obtener_ruta_local(key: str) -> str:
    # Si usa R2, descarga a un temp para que el procesador de PDF pueda leerlo en modo síncrono.
    # Llamar liberar_ruta_local() cuando termine.
    if _r2_habilitado():
        contenido = await descargar(key)
        ext = os.path.splitext(key)[1] or ".pdf"
        tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
        tmp.write(contenido)
        tmp.close()
        return tmp.name
    else:
        return os.path.join(settings.UPLOAD_DIR, key)


def liberar_ruta_local(ruta: str) -> None:
    if _r2_habilitado():
        try:
            os.remove(ruta)
        except OSError:
            pass
