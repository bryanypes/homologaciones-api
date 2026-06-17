"""
Servicio de email para notificaciones del sistema de homologaciones.

Usa aiosmtplib para envío asíncrono. Las plantillas están en este mismo módulo
para evitar dependencias de archivos externos y simplificar el despliegue.

Instalar: uv add aiosmtplib
"""

import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

# FIX: import al nivel del módulo para que @patch("app.services.email_service.aiosmtplib")
# funcione correctamente en los tests. El import tardío dentro de _enviar impedía el patcheo.
import aiosmtplib

from app.core.config import settings

logger = logging.getLogger(__name__)

# Mapa de estados a descripciones legibles en español
ESTADO_LABELS = {
    "borrador": "Borrador",
    "enviada": "Enviada — en espera de revisión",
    "en_revision": "En revisión por coordinador",
    "procesando_ia": "Procesando con inteligencia artificial",
    "pendiente_rector": "Pendiente de aprobación por rectoría",
    "aprobada": "Aprobada ✓",
    "rechazada": "Rechazada",
}

# ──────────────────────────────────────────────────────────────
# Plantillas HTML
# ──────────────────────────────────────────────────────────────

_BASE_STYLE = """
    body { font-family: Arial, sans-serif; background: #f4f4f4; margin: 0; padding: 0; }
    .container { max-width: 600px; margin: 40px auto; background: #fff;
                 border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,.1); }
    .header { background: #003366; color: #fff; padding: 24px 32px; }
    .header h1 { margin: 0; font-size: 20px; }
    .body { padding: 32px; color: #333; line-height: 1.6; }
    .estado-badge { display: inline-block; background: #e8f0fe; color: #1a56db;
                    padding: 6px 16px; border-radius: 20px; font-weight: bold; margin: 12px 0; }
    .footer { background: #f9f9f9; padding: 16px 32px; font-size: 12px; color: #888;
              border-top: 1px solid #eee; }
    .btn { display: inline-block; background: #003366; color: #fff; padding: 12px 24px;
           border-radius: 4px; text-decoration: none; margin-top: 16px; }
"""


def _html_cambio_estado(
    nombre_estudiante: str,
    solicitud_id: str,
    estado_anterior: str,
    estado_nuevo: str,
    observacion: Optional[str],
) -> str:
    label_nuevo = ESTADO_LABELS.get(estado_nuevo, estado_nuevo)
    label_anterior = ESTADO_LABELS.get(estado_anterior, estado_anterior)

    obs_html = (
        f"<p><strong>Observación:</strong> {observacion}</p>"
        if observacion
        else ""
    )

    aprobada = estado_nuevo == "aprobada"
    rechazada = estado_nuevo == "rechazada"
    color_badge = "#d4edda" if aprobada else ("#f8d7da" if rechazada else "#e8f0fe")
    color_text = "#155724" if aprobada else ("#721c24" if rechazada else "#1a56db")

    return f"""
    <!DOCTYPE html><html><head><meta charset="utf-8">
    <style>{_BASE_STYLE}
    .estado-badge {{ background: {color_badge}; color: {color_text}; }}
    </style></head><body>
    <div class="container">
      <div class="header">
        <h1>Sistema de Homologaciones — Universidad del Cauca</h1>
      </div>
      <div class="body">
        <p>Estimado/a <strong>{nombre_estudiante}</strong>,</p>
        <p>Su solicitud de homologación ha cambiado de estado:</p>
        <p>Estado anterior: <em>{label_anterior}</em></p>
        <p>Estado actual:</p>
        <span class="estado-badge">{label_nuevo}</span>
        {obs_html}
        <p>Puede consultar el detalle de su solicitud en el sistema.</p>
        <p><strong>ID de solicitud:</strong> <code>{solicitud_id}</code></p>
      </div>
      <div class="footer">
        Este es un mensaje automático. Por favor no responda a este correo.
        Sistema de Homologaciones — Oficina de Registro y Control Académico.
      </div>
    </div>
    </body></html>
    """


def _html_homologacion_completada(
    nombre_estudiante: str,
    solicitud_id: str,
    tokens_utilizados: int,
) -> str:
    return f"""
    <!DOCTYPE html><html><head><meta charset="utf-8">
    <style>{_BASE_STYLE}</style></head><body>
    <div class="container">
      <div class="header">
        <h1>Sistema de Homologaciones — Universidad del Cauca</h1>
      </div>
      <div class="body">
        <p>Estimado/a <strong>{nombre_estudiante}</strong>,</p>
        <p>El análisis de inteligencia artificial de su solicitud ha finalizado exitosamente.</p>
        <span class="estado-badge">Pendiente de aprobación por rectoría</span>
        <p>El resultado ha sido enviado al rector para su revisión y aprobación final.
           Le notificaremos cuando haya una decisión.</p>
        <p><strong>ID de solicitud:</strong> <code>{solicitud_id}</code></p>
      </div>
      <div class="footer">
        Este es un mensaje automático. Por favor no responda a este correo.
      </div>
    </div>
    </body></html>
    """


def _texto_plano_cambio_estado(
    nombre_estudiante: str,
    solicitud_id: str,
    estado_nuevo: str,
    observacion: Optional[str],
) -> str:
    label = ESTADO_LABELS.get(estado_nuevo, estado_nuevo)
    obs = f"\nObservación: {observacion}" if observacion else ""
    return (
        f"Estimado/a {nombre_estudiante},\n\n"
        f"Su solicitud de homologación (ID: {solicitud_id}) "
        f"ha cambiado al estado: {label}.{obs}\n\n"
        "Sistema de Homologaciones — Universidad del Cauca"
    )


# ──────────────────────────────────────────────────────────────
# Funciones de envío
# ──────────────────────────────────────────────────────────────

def _email_configurado() -> bool:
    return all([
        settings.SMTP_HOST,
        settings.SMTP_USER,
        settings.SMTP_PASSWORD,
        settings.EMAIL_FROM,
    ])


async def _enviar(destinatario: str, asunto: str, html: str, texto: str) -> None:
    """Función base de envío. Falla silenciosamente si el SMTP no está configurado."""
    if not _email_configurado():
        logger.warning(
            "[Email] SMTP no configurado. Saltando envío a %s. Asunto: %s",
            destinatario,
            asunto,
        )
        return

    # FIX: eliminado el `import aiosmtplib` tardío que estaba dentro del try.
    # El import al nivel del módulo es suficiente y permite que el patch de tests funcione.
    try:
        mensaje = MIMEMultipart("alternative")
        mensaje["Subject"] = asunto
        mensaje["From"] = settings.EMAIL_FROM
        mensaje["To"] = destinatario
        mensaje.attach(MIMEText(texto, "plain", "utf-8"))
        mensaje.attach(MIMEText(html, "html", "utf-8"))

        await aiosmtplib.send(
            mensaje,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            start_tls=True,
        )
        logger.info("[Email] Enviado a %s — %s", destinatario, asunto)

    except Exception as exc:
        # No propagamos el error para que no rompa el flujo principal
        logger.error("[Email] Error al enviar a %s: %s", destinatario, exc)


async def notificar_cambio_estado(
    email_estudiante: str,
    nombre_estudiante: str,
    solicitud_id: str,
    estado_anterior: str,
    estado_nuevo: str,
    observacion: Optional[str] = None,
) -> None:
    """
    Notifica al estudiante que su solicitud cambió de estado.
    Llamar desde el worker de Kafka en handle_cambio_estado.
    """
    label = ESTADO_LABELS.get(estado_nuevo, estado_nuevo)
    asunto = f"[Homologaciones] Su solicitud cambió a: {label}"
    html = _html_cambio_estado(
        nombre_estudiante, solicitud_id, estado_anterior, estado_nuevo, observacion
    )
    texto = _texto_plano_cambio_estado(
        nombre_estudiante, solicitud_id, estado_nuevo, observacion
    )
    await _enviar(email_estudiante, asunto, html, texto)


async def notificar_homologacion_completada(
    email_estudiante: str,
    nombre_estudiante: str,
    solicitud_id: str,
    tokens_utilizados: int,
) -> None:
    """
    Notifica al estudiante que el análisis IA finalizó y está pendiente del rector.
    Llamar desde el worker de Kafka en handle_homologacion_completada.
    """
    asunto = "[Homologaciones] Análisis completado — Pendiente de aprobación"
    html = _html_homologacion_completada(nombre_estudiante, solicitud_id, tokens_utilizados)
    texto = (
        f"Estimado/a {nombre_estudiante},\n\n"
        f"El análisis de su solicitud (ID: {solicitud_id}) ha finalizado. "
        "Está pendiente de aprobación por rectoría.\n\n"
        "Sistema de Homologaciones — Universidad del Cauca"
    )
    await _enviar(email_estudiante, asunto, html, texto)