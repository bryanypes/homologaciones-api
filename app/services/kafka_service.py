from kafka import KafkaProducer, KafkaConsumer
from kafka.errors import KafkaError
import json
from app.core.config import settings

TOPIC_SOLICITUDES = "solicitudes"
TOPIC_HOMOLOGACIONES = "homologaciones"


def get_producer() -> KafkaProducer:
    return KafkaProducer(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8") if k else None,
    )


def publicar_evento(topic: str, key: str, payload: dict) -> None:
    try:
        producer = get_producer()
        producer.send(topic, key=key, value=payload)
        producer.flush()
        producer.close()
    except KafkaError as e:
        print(f"[Kafka] Error publicando evento en {topic}: {e}")


def publicar_cambio_estado(solicitud_id: str, estado_anterior: str, estado_nuevo: str, usuario_id: str) -> None:
    publicar_evento(
        topic=TOPIC_SOLICITUDES,
        key=solicitud_id,
        payload={
            "solicitud_id": solicitud_id,
            "estado_anterior": estado_anterior,
            "estado_nuevo": estado_nuevo,
            "usuario_id": usuario_id,
        },
    )


def publicar_homologacion_completada(solicitud_id: str, homologacion_id: str, tokens: int) -> None:
    publicar_evento(
        topic=TOPIC_HOMOLOGACIONES,
        key=solicitud_id,
        payload={
            "solicitud_id": solicitud_id,
            "homologacion_id": homologacion_id,
            "tokens_utilizados": tokens,
        },
    )