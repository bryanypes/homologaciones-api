from kafka import KafkaProducer
from kafka.errors import KafkaError
import json
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

TOPIC_SOLICITUDES = "solicitudes"
TOPIC_HOMOLOGACIONES = "homologaciones"

_producer: KafkaProducer | None = None


def _get_producer() -> KafkaProducer:
    global _producer
    if _producer is None:
        _producer = KafkaProducer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            linger_ms=5,
            retries=3,
        )
    return _producer


def publicar_evento(topic: str, key: str, payload: dict) -> None:
    try:
        producer = _get_producer()
        producer.send(topic, key=key, value=payload)
        producer.flush()
    except KafkaError as e:
        logger.warning("[Kafka] Error publicando en %s: %s", topic, e)


def publicar_cambio_estado(
    solicitud_id: str,
    estado_anterior: str,
    estado_nuevo: str,
    usuario_id: str,
    email_estudiante: str = "",
    nombre_estudiante: str = "",
    observacion: str = None,
):
    publicar_evento(
        topic=TOPIC_SOLICITUDES,
        key=solicitud_id,
        payload={
            "solicitud_id": solicitud_id,
            "estado_anterior": estado_anterior,
            "estado_nuevo": estado_nuevo,
            "usuario_id": usuario_id,
            "email_estudiante": email_estudiante,
            "nombre_estudiante": nombre_estudiante,
            "observacion": observacion,
        },
    )


def publicar_homologacion_completada(
    solicitud_id: str,
    homologacion_id: str,
    tokens: int,
    email_estudiante: str = "",
    nombre_estudiante: str = "",
) -> None:
    publicar_evento(
        topic=TOPIC_HOMOLOGACIONES,
        key=solicitud_id,
        payload={
            "solicitud_id": solicitud_id,
            "homologacion_id": homologacion_id,
            "tokens_utilizados": tokens,
            "email_estudiante": email_estudiante,
            "nombre_estudiante": nombre_estudiante,
        },
    )
