import asyncio
import json
import logging
import threading

from kafka import KafkaConsumer
from kafka.errors import KafkaError

from app.core.config import settings
from app.services.kafka_service import TOPIC_SOLICITUDES, TOPIC_HOMOLOGACIONES
from app.services.email_service import (
    notificar_cambio_estado,
    notificar_homologacion_completada,
)

logger = logging.getLogger(__name__)


def _run_async(coro) -> None:
    """Ejecuta una corutina desde un contexto síncrono (thread)."""
    try:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(coro)
        loop.close()
    except Exception as exc:
        logger.error("[Worker] Error al ejecutar corutina async: %s", exc)


def handle_cambio_estado(mensaje: dict) -> None:
    """
    Payload esperado (publicado por kafka_service.publicar_cambio_estado):
    {
        "solicitud_id": str,
        "estado_anterior": str,
        "estado_nuevo": str,
        "usuario_id": str,
        "email_estudiante": str,       ← requerido para notificar
        "nombre_estudiante": str,      ← requerido para notificar
        "observacion": str | None
    }
    """
    solicitud_id = mensaje.get("solicitud_id", "")
    estado_nuevo = mensaje.get("estado_nuevo", "")
    estado_anterior = mensaje.get("estado_anterior", "")
    email = mensaje.get("email_estudiante")
    nombre = mensaje.get("nombre_estudiante")
    observacion = mensaje.get("observacion")

    logger.info("[Worker] Cambio de estado: %s → %s", solicitud_id, estado_nuevo)

    if not email or not nombre:
        logger.warning(
            "[Worker] Evento sin email/nombre del estudiante. "
            "Verifica que kafka_service incluya esos campos. solicitud_id=%s",
            solicitud_id,
        )
        return

    _run_async(
        notificar_cambio_estado(
            email_estudiante=email,
            nombre_estudiante=nombre,
            solicitud_id=solicitud_id,
            estado_anterior=estado_anterior,
            estado_nuevo=estado_nuevo,
            observacion=observacion,
        )
    )


def handle_homologacion_completada(mensaje: dict) -> None:
    """
    Payload esperado (publicado por kafka_service.publicar_homologacion_completada):
    {
        "solicitud_id": str,
        "tokens_utilizados": int,
        "email_estudiante": str,
        "nombre_estudiante": str
    }
    """
    solicitud_id = mensaje.get("solicitud_id", "")
    tokens = mensaje.get("tokens_utilizados", 0)
    email = mensaje.get("email_estudiante")
    nombre = mensaje.get("nombre_estudiante")

    logger.info("[Worker] Homologación completada: %s tokens=%s", solicitud_id, tokens)

    if not email or not nombre:
        logger.warning(
            "[Worker] Evento sin email/nombre del estudiante. solicitud_id=%s",
            solicitud_id,
        )
        return

    _run_async(
        notificar_homologacion_completada(
            email_estudiante=email,
            nombre_estudiante=nombre,
            solicitud_id=solicitud_id,
            tokens_utilizados=tokens,
        )
    )


def iniciar_worker() -> None:
    try:
        consumer = KafkaConsumer(
            TOPIC_SOLICITUDES,
            TOPIC_HOMOLOGACIONES,
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            group_id="homologaciones-workers",
            auto_offset_reset="earliest",
        )
        logger.info("[Worker] Escuchando eventos Kafka en %s...", settings.KAFKA_BOOTSTRAP_SERVERS)

        for mensaje in consumer:
            topic = mensaje.topic
            payload = mensaje.value
            try:
                if topic == TOPIC_SOLICITUDES:
                    handle_cambio_estado(payload)
                elif topic == TOPIC_HOMOLOGACIONES:
                    handle_homologacion_completada(payload)
            except Exception as exc:
                logger.error("[Worker] Error procesando mensaje de %s: %s", topic, exc)

    except KafkaError as e:
        logger.error("[Worker] Error al conectar con Kafka: %s", e)
    except Exception as e:
        logger.error("[Worker] Error inesperado en worker: %s", e)


def iniciar_worker_en_background() -> None:
    thread = threading.Thread(target=iniciar_worker, daemon=True, name="kafka-worker")
    thread.start()
    logger.info("[Worker] Thread Kafka iniciado en background")