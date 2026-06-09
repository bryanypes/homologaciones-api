import json
import threading
from kafka import KafkaConsumer
from kafka.errors import KafkaError
from app.core.config import settings
from app.services.kafka_service import TOPIC_SOLICITUDES, TOPIC_HOMOLOGACIONES


def handle_cambio_estado(mensaje: dict) -> None:
    print(f"[Worker] Cambio de estado: {mensaje['solicitud_id']} → {mensaje['estado_nuevo']}")


def handle_homologacion_completada(mensaje: dict) -> None:
    print(f"[Worker] Homologación completada: {mensaje['solicitud_id']} tokens={mensaje['tokens_utilizados']}")


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
        print("[Worker] Escuchando eventos Kafka...")
        for mensaje in consumer:
            topic = mensaje.topic
            payload = mensaje.value
            if topic == TOPIC_SOLICITUDES:
                handle_cambio_estado(payload)
            elif topic == TOPIC_HOMOLOGACIONES:
                handle_homologacion_completada(payload)
    except KafkaError as e:
        print(f"[Worker] Error en consumer: {e}")


def iniciar_worker_en_background() -> None:
    thread = threading.Thread(target=iniciar_worker, daemon=True)
    thread.start()