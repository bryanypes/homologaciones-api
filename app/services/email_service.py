import logging
from typing import Optional

import resend

from app.core.config import settings

logger = logging.getLogger(__name__)

# Mapa de estados a descripciones legibles en español
ESTADO_LABELS = {
    "borrador": "Borrador",
    "enviada": "Enviada — en espera de revisión",
    "en_revision": "En revisión por coordinador",
    "procesando_ia": "Procesando con inteligencia artificial",
    "pendiente_rector": "Pendiente de aprobación por vicerrectoría",
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
    .code-box { background: #f0f0f0; padding: 12px; border-radius: 4px; 
                font-family: monospace; word-break: break-all; margin: 12px 0; }
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
        <span class="estado-badge">Pendiente de aprobación por vicerrectoría</span>
        <p>El resultado ha sido enviado al vicerrector académico para su revisión y aprobación final.
           Le notificaremos cuando haya una decisión.</p>
        <p><strong>ID de solicitud:</strong> <code>{solicitud_id}</code></p>
      </div>
      <div class="footer">
        Este es un mensaje automático. Por favor no responda a este correo.
      </div>
    </div>
    </body></html>
    """


def _html_recuperacion_contraseña(
    nombre_usuario: str,
    token: str,
    frontend_url: str = "http://localhost:3000",
) -> str:
    """Plantilla HTML para recuperación de contraseña"""
    enlace = f"{frontend_url}/resetear-contraseña?token={token}"
    
    return f"""
    <!DOCTYPE html><html><head><meta charset="utf-8">
    <style>{_BASE_STYLE}</style></head><body>
    <div class="container">
      <div class="header">
        <h1>Sistema de Homologaciones — Universidad del Cauca</h1>
      </div>
      <div class="body">
        <p>Estimado/a <strong>{nombre_usuario}</strong>,</p>
        <p>Recibimos una solicitud para restablecer tu contraseña. 
           Si no la solicitaste, ignora este correo.</p>
        
        <p><strong>Tu token de recuperación:</strong></p>
        <div class="code-box">{token}</div>
        
        <p>Este token es válido por 30 minutos. Accede a tu cuenta con el siguiente enlace:</p>
        <a href="{enlace}" class="btn">Restablecer Contraseña</a>
        
        <p>O copia el token anterior en el formulario de recuperación si accedes directamente.</p>
      </div>
      <div class="footer">
        Este es un mensaje automático. Por favor no responda a este correo.
        Sistema de Homologaciones — Oficina de Registro y Control Académico.
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


def _texto_plano_recuperacion_contraseña(
    nombre_usuario: str,
    token: str,
) -> str:
    """Plantilla de texto plano para recuperación de contraseña"""
    return (
        f"Estimado/a {nombre_usuario},\n\n"
        f"Tu token de recuperación de contraseña es:\n{token}\n\n"
        "Este token es válido por 30 minutos.\n\n"
        "Sistema de Homologaciones — Universidad del Cauca"
    )


# ──────────────────────────────────────────────────────────────
# Funciones de envío
# ──────────────────────────────────────────────────────────────

async def _enviar(destinatario: str, asunto: str, html: str, texto: str) -> None:
    """Envía email via Resend HTTP API. Falla silenciosamente si no está configurado."""
    if not settings.RESEND_API_KEY:
        logger.warning("[Email] RESEND_API_KEY no configurada. Saltando envío a %s.", destinatario)
        return

    try:
        resend.api_key = settings.RESEND_API_KEY
        email_from = settings.EMAIL_FROM or "Sistema Homologaciones <onboarding@resend.dev>"
        resend.Emails.send({
            "from": email_from,
            "to": [destinatario],
            "subject": asunto,
            "html": html,
            "text": texto,
        })
        logger.info("[Email] Enviado a %s — %s", destinatario, asunto)
    except Exception as exc:
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
    html = _html_homologacion_completada(nombre_estudiante, solicitud_id)
    texto = (
        f"Estimado/a {nombre_estudiante},\n\n"
        f"El análisis de su solicitud (ID: {solicitud_id}) ha finalizado. "
        "Está pendiente de aprobación por vicerrectoría.\n\n"
        "Sistema de Homologaciones — Universidad del Cauca"
    )
    await _enviar(email_estudiante, asunto, html, texto)


async def notificar_mercadeo_homologacion_aprobada(
    nombre_estudiante: str,
    solicitud_id: str,
    numero_resolucion: str,
    programa_destino: str,
    institucion_origen: str,
) -> None:
    """
    Notifica al área de mercadeo que una homologación fue aprobada.
    El destinatario se configura con la variable MERCADEO_EMAIL.
    """
    destinatario = settings.MERCADEO_EMAIL
    if not destinatario:
        logger.info("[Email] MERCADEO_EMAIL no configurado. Saltando notificación a mercadeo.")
        return

    asunto = f"[Homologaciones] Aprobada — Resolución {numero_resolucion}"
    html = f"""
    <!DOCTYPE html><html><head><meta charset="utf-8">
    <style>{_BASE_STYLE}</style></head><body>
    <div class="container">
      <div class="header">
        <h1>Sistema de Homologaciones — Universidad del Cauca</h1>
      </div>
      <div class="body">
        <p>Se ha aprobado una solicitud de homologación. Por favor tome nota de los datos para el proceso de matrícula:</p>
        <p><strong>Estudiante:</strong> {nombre_estudiante}</p>
        <p><strong>Programa destino:</strong> {programa_destino}</p>
        <p><strong>Institución de origen:</strong> {institucion_origen}</p>
        <span class="estado-badge" style="background:#d4edda;color:#155724;">Resolución {numero_resolucion} — APROBADA</span>
        <p><strong>ID de solicitud:</strong> <code>{solicitud_id}</code></p>
        <p>El estudiante puede iniciar su proceso de matrícula.</p>
      </div>
      <div class="footer">
        Este es un mensaje automático del Sistema de Homologaciones.
      </div>
    </div>
    </body></html>
    """
    texto = (
        f"Homologación aprobada — Resolución {numero_resolucion}\n\n"
        f"Estudiante: {nombre_estudiante}\n"
        f"Programa destino: {programa_destino}\n"
        f"Institución de origen: {institucion_origen}\n"
        f"ID solicitud: {solicitud_id}\n\n"
        "El estudiante puede iniciar su proceso de matrícula.\n\n"
        "Sistema de Homologaciones — Universidad del Cauca"
    )
    await _enviar(destinatario, asunto, html, texto)


async def enviar_recuperacion_contraseña(
    email_usuario: str,
    nombre_usuario: str,
    token: str,
    frontend_url: str = "http://localhost:3000",
) -> None:
    """
    Envía el token de recuperación de contraseña al usuario.
    """
    asunto = "[Homologaciones] Recuperación de contraseña"
    html = _html_recuperacion_contraseña(nombre_usuario, token, frontend_url)
    texto = _texto_plano_recuperacion_contraseña(nombre_usuario, token)
    await _enviar(email_usuario, asunto, html, texto)