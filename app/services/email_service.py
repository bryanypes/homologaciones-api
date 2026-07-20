import logging
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

ESTADO_LABELS = {
    "borrador":             "Borrador",
    "enviada":              "Enviada",
    "en_revision":          "En revisión",
    "revision_coordinador": "Revisión del coordinador",
    "procesando_ia":        "Procesando con IA",
    "pendiente_rector":     "Pendiente del vicerrector",
    "aprobada":             "Aprobada",
    "rechazada":            "Rechazada",
}

_BADGE = {
    "aprobada":             "background:#E8F4E9;color:#3F7D45",
    "rechazada":            "background:#FAE8E6;color:#B33B2E",
    "pendiente_rector":     "background:#E6EBF3;color:#053686",
    "revision_coordinador": "background:#F2F0E8;color:#4B4B49",
    "en_revision":          "background:#F2F0E8;color:#4B4B49",
    "procesando_ia":        "background:#FEFCF4;color:#C1AB1F",
    "enviada":              "background:#E6EBF3;color:#053686",
    "borrador":             "background:#F2F0E8;color:#6D6C69",
}

# Qué mascota usar según el estado de la solicitud
_MASCOTA_ESTADO = {
    "aprobada":             "Iaaprobada.png",
    "rechazada":            "Iaerror.png",
    "procesando_ia":        "Iapensando.png",
    "pendiente_rector":     "Iapensando.png",
    "en_revision":          "Iapensando.png",
    "revision_coordinador": "Iapensando.png",
    "enviada":              "IAsaludando.png",
    "borrador":             "IAsaludando.png",
}

def _img_url(nombre: str) -> str:
    return f"{settings.BASE_URL}/static/email/{nombre}"


_CSS = """
  *{box-sizing:border-box;margin:0;padding:0}
  body{
    background:#FFFDF5;
    font-family:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
    -webkit-font-smoothing:antialiased;
  }
  .wrap{padding:40px 16px;background:#FFFDF5}
  .card{
    max-width:560px;margin:0 auto;background:#fff;
    border-radius:16px;overflow:hidden;
    box-shadow:0 4px 32px rgba(5,54,134,.09);
  }
  .hdr{background:#053686;padding:24px 32px}
  .hdr-row{display:flex;align-items:center;gap:12px}
  .hdr-logo{width:36px;height:36px;flex-shrink:0}
  .hdr-logo img{width:100%;height:100%;object-fit:contain}
  .hdr-name{color:#fff;font-size:18px;font-weight:600;letter-spacing:-.2px}
  .mascot{background:#F3F5F9;padding:24px;text-align:center}
  .mascot img{height:88px;width:auto}
  .body{padding:32px}
  .greeting{font-size:16px;font-weight:600;color:#1E1E1E;margin-bottom:12px}
  .text{font-size:14px;color:#4B4B49;line-height:1.65}
  .mt{margin-top:12px}
  .badge{
    display:inline-block;margin:20px 0;
    padding:7px 18px;border-radius:100px;
    font-size:13px;font-weight:500;
  }
  .obs{
    margin-top:16px;padding:12px 16px;
    background:#FEFCF4;border:1px solid #F5ECB2;
    border-radius:10px;font-size:14px;color:#4B4B49;
  }
  .id-box{
    margin-top:20px;padding:12px 16px;
    background:#F3F5F9;border-radius:10px;
    border-left:3px solid #053686;
    font-size:12px;color:#6D6C69;
  }
  .id-box code{font-family:'Courier New',monospace;color:#053686;font-weight:600}
  .code-box{
    margin:16px 0;padding:18px;background:#F3F5F9;
    border-radius:12px;font-family:'Courier New',monospace;
    font-size:18px;font-weight:700;color:#053686;
    letter-spacing:3px;text-align:center;word-break:break-all;
  }
  .btn{
    display:inline-block;margin-top:20px;
    padding:12px 24px;background:#053686;color:#fff;
    text-decoration:none;border-radius:12px;
    font-size:14px;font-weight:500;
  }
  .footer{
    background:#F2F0E8;border-top:1px solid #E4E2DB;
    padding:16px 32px;font-size:11px;color:#8F8E8A;
    text-align:center;line-height:1.6;
  }
"""


def _email(body_html: str, mascota: str = "IAsaludando.png") -> str:
    logo_tag = f'<img src="{_img_url("LOGO.png")}" alt="HomologaIA" style="width:36px;height:36px;object-fit:contain" />'
    mascota_tag = f'<img src="{_img_url(mascota)}" alt="" style="height:88px;width:auto" />'
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">
  <div class="card">
    <div class="hdr">
      <div class="hdr-row">
        <div class="hdr-logo">{logo_tag}</div>
        <span class="hdr-name">HomologaIA</span>
      </div>
    </div>
    <div class="mascot">{mascota_tag}</div>
    <div class="body">
{body_html}
    </div>
    <div class="footer">
      Mensaje automático · HomologaIA · Corporación Universitaria Autónoma del Cauca<br>
      Por favor no responda directamente a este correo.
    </div>
  </div>
</div>
</body>
</html>"""


def _html_cambio_estado(
    nombre_estudiante: str,
    solicitud_id: str,
    estado_anterior: str,
    estado_nuevo: str,
    observacion: Optional[str],
) -> str:
    label = ESTADO_LABELS.get(estado_nuevo, estado_nuevo)
    label_ant = ESTADO_LABELS.get(estado_anterior, estado_anterior)
    badge = _BADGE.get(estado_nuevo, "background:#E6EBF3;color:#053686")
    obs = f'<div class="obs"><strong>Observación:</strong> {observacion}</div>' if observacion else ""
    mascota = _MASCOTA_ESTADO.get(estado_nuevo, "IAsaludando.png")

    body = f"""      <p class="greeting">Hola, {nombre_estudiante}</p>
      <p class="text">Tu solicitud de homologación ha cambiado de estado.</p>
      <p class="text mt">Estado anterior: <strong>{label_ant}</strong></p>
      <p class="text">Nuevo estado:</p>
      <span class="badge" style="{badge}">{label}</span>
      {obs}
      <div class="id-box">Solicitud: <code>{solicitud_id}</code></div>"""
    return _email(body, mascota)


def _html_homologacion_completada(nombre_estudiante: str, solicitud_id: str) -> str:
    badge = _BADGE["pendiente_rector"]
    body = f"""      <p class="greeting">Hola, {nombre_estudiante}</p>
      <p class="text">El análisis de inteligencia artificial de tu solicitud ha finalizado.</p>
      <span class="badge" style="{badge}">Pendiente del vicerrector</span>
      <p class="text">El resultado fue enviado al vicerrector académico para revisión y aprobación final.<br>
      Te notificaremos cuando haya una decisión.</p>
      <div class="id-box">Solicitud: <code>{solicitud_id}</code></div>"""
    return _email(body, "Iapensando.png")


def _html_recuperacion_contraseña(
    nombre_usuario: str,
    token: str,
    frontend_url: str = "http://localhost:3000",
) -> str:
    enlace = f"{frontend_url}/resetear-contraseña?token={token}"
    body = f"""      <p class="greeting">Hola, {nombre_usuario}</p>
      <p class="text">Recibimos una solicitud para restablecer tu contraseña. Si no la solicitaste, ignora este correo.</p>
      <p class="text mt">Tu token de recuperación (válido 30 minutos):</p>
      <div class="code-box">{token}</div>
      <p class="text">O accede directamente con el siguiente enlace:</p>
      <a href="{enlace}" class="btn">Restablecer contraseña</a>"""
    return _email(body, "IAseñalandoderecha.png")


def _html_mercadeo_aprobada(
    nombre_estudiante: str,
    solicitud_id: str,
    numero_resolucion: str,
    programa_destino: str,
    institucion_origen: str,
) -> str:
    badge = _BADGE["aprobada"]
    body = f"""      <p class="greeting">Nueva homologación aprobada</p>
      <span class="badge" style="{badge}">Resolución {numero_resolucion}</span>
      <p class="text"><strong>Estudiante:</strong> {nombre_estudiante}</p>
      <p class="text mt"><strong>Programa destino:</strong> {programa_destino}</p>
      <p class="text"><strong>Institución de origen:</strong> {institucion_origen}</p>
      <div class="id-box">Solicitud: <code>{solicitud_id}</code></div>
      <p class="text mt">El estudiante puede iniciar su proceso de matrícula.</p>"""
    return _email(body, "Iaaprobada.png")


def _texto_plano_cambio_estado(
    nombre_estudiante: str,
    solicitud_id: str,
    estado_nuevo: str,
    observacion: Optional[str],
) -> str:
    label = ESTADO_LABELS.get(estado_nuevo, estado_nuevo)
    obs = f"\nObservación: {observacion}" if observacion else ""
    return (
        f"Hola, {nombre_estudiante}.\n\n"
        f"Tu solicitud de homologación (ID: {solicitud_id}) "
        f"cambió al estado: {label}.{obs}\n\n"
        "HomologaIA — Corporación Universitaria Autónoma del Cauca"
    )


def _texto_plano_recuperacion_contraseña(nombre_usuario: str, token: str) -> str:
    return (
        f"Hola, {nombre_usuario}.\n\n"
        f"Tu token de recuperación de contraseña es:\n{token}\n\n"
        "Válido por 30 minutos.\n\n"
        "HomologaIA — Corporación Universitaria Autónoma del Cauca"
    )


async def _enviar(destinatario: str, asunto: str, html: str, texto: str) -> None:
    if not settings.BREVO_API_KEY:
        logger.warning("[Email] BREVO_API_KEY no configurada. Saltando envío a %s.", destinatario)
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                "https://api.brevo.com/v3/smtp/email",
                headers={"api-key": settings.BREVO_API_KEY, "content-type": "application/json"},
                json={
                    "sender": {"name": "HomologaIA", "email": settings.EMAIL_FROM},
                    "to": [{"email": destinatario}],
                    "subject": asunto,
                    "htmlContent": html,
                    "textContent": texto,
                },
            )
            r.raise_for_status()
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
    label = ESTADO_LABELS.get(estado_nuevo, estado_nuevo)
    asunto = f"[HomologaIA] Tu solicitud cambió a: {label}"
    html = _html_cambio_estado(nombre_estudiante, solicitud_id, estado_anterior, estado_nuevo, observacion)
    texto = _texto_plano_cambio_estado(nombre_estudiante, solicitud_id, estado_nuevo, observacion)
    await _enviar(email_estudiante, asunto, html, texto)


async def notificar_homologacion_completada(
    email_estudiante: str,
    nombre_estudiante: str,
    solicitud_id: str,
    tokens_utilizados: int,
) -> None:
    asunto = "[HomologaIA] Análisis completado — Pendiente de aprobación"
    html = _html_homologacion_completada(nombre_estudiante, solicitud_id)
    texto = (
        f"Hola, {nombre_estudiante}.\n\n"
        f"El análisis de tu solicitud (ID: {solicitud_id}) ha finalizado. "
        "Está pendiente de aprobación por vicerrectoría.\n\n"
        "HomologaIA — Corporación Universitaria Autónoma del Cauca"
    )
    await _enviar(email_estudiante, asunto, html, texto)


async def notificar_mercadeo_homologacion_aprobada(
    nombre_estudiante: str,
    solicitud_id: str,
    numero_resolucion: str,
    programa_destino: str,
    institucion_origen: str,
) -> None:
    destinatario = settings.MERCADEO_EMAIL
    if not destinatario:
        logger.info("[Email] MERCADEO_EMAIL no configurado. Saltando notificación a mercadeo.")
        return

    asunto = f"[HomologaIA] Homologación aprobada — Resolución {numero_resolucion}"
    html = _html_mercadeo_aprobada(
        nombre_estudiante, solicitud_id, numero_resolucion, programa_destino, institucion_origen
    )
    texto = (
        f"Homologación aprobada — Resolución {numero_resolucion}\n\n"
        f"Estudiante: {nombre_estudiante}\n"
        f"Programa destino: {programa_destino}\n"
        f"Institución de origen: {institucion_origen}\n"
        f"ID solicitud: {solicitud_id}\n\n"
        "El estudiante puede iniciar su proceso de matrícula.\n\n"
        "HomologaIA — Corporación Universitaria Autónoma del Cauca"
    )
    await _enviar(destinatario, asunto, html, texto)


async def enviar_recuperacion_contraseña(
    email_usuario: str,
    nombre_usuario: str,
    token: str,
    frontend_url: str = "http://localhost:3000",
) -> None:
    asunto = "[HomologaIA] Recuperación de contraseña"
    html = _html_recuperacion_contraseña(nombre_usuario, token, frontend_url)
    texto = _texto_plano_recuperacion_contraseña(nombre_usuario, token)
    await _enviar(email_usuario, asunto, html, texto)
