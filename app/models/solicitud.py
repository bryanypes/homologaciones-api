import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Text, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base
import enum


class EstadoSolicitud(str, enum.Enum):
    BORRADOR = "borrador"
    ENVIADA = "enviada"
    EN_REVISION = "en_revision"
    PROCESANDO_IA = "procesando_ia"
    PENDIENTE_RECTOR = "pendiente_rector"
    APROBADA = "aprobada"
    RECHAZADA = "rechazada"


class Solicitud(Base):
    __tablename__ = "solicitudes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    estudiante_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False
    )

    # ── Datos personales del estudiante al momento de la solicitud ───────────
    # Se guardan aquí para que la resolución refleje los datos exactos en ese
    # momento, aunque el usuario actualice su perfil después.
    cedula: Mapped[str] = mapped_column(String(20), nullable=True)
    telefono: Mapped[str] = mapped_column(String(20), nullable=True)
    correo_contacto: Mapped[str] = mapped_column(String(255), nullable=True)

    # ── Programa de origen (institución de la que viene el estudiante) ────────
    institucion_origen: Mapped[str] = mapped_column(String(255), nullable=True)
    programa_origen: Mapped[str] = mapped_column(String(255), nullable=True)

    # ── Programa de destino (Uniautónoma) ─────────────────────────────────────
    institucion_destino: Mapped[str] = mapped_column(String(255), nullable=True)
    programa_destino: Mapped[str] = mapped_column(String(255), nullable=True)

    # FK opcionales al catálogo (si el programa existe en BD)
    programa_origen_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("programas.id"), nullable=True
    )
    programa_destino_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("programas.id"), nullable=True
    )

    # ── Estado y auditoría ───────────────────────────────────────────────────
    estado: Mapped[EstadoSolicitud] = mapped_column(
        SAEnum(EstadoSolicitud, values_callable=lambda x: [e.value for e in x]),
        default=EstadoSolicitud.BORRADOR
    )
    observaciones: Mapped[str] = mapped_column(Text, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # ── Relaciones ───────────────────────────────────────────────────────────
    estudiante: Mapped["Usuario"] = relationship(
        "Usuario", foreign_keys=[estudiante_id]
    )
    programa_origen_rel: Mapped["Programa"] = relationship(
        "Programa", foreign_keys=[programa_origen_id]
    )
    programa_destino_rel: Mapped["Programa"] = relationship(
        "Programa", foreign_keys=[programa_destino_id]
    )
    documentos: Mapped[list["Documento"]] = relationship(
        "Documento", back_populates="solicitud"
    )
    homologacion: Mapped["Homologacion"] = relationship(
        "Homologacion", back_populates="solicitud", uselist=False
    )
    historial: Mapped[list["HistorialEstado"]] = relationship(
        "HistorialEstado", back_populates="solicitud"
    )


class HistorialEstado(Base):
    __tablename__ = "historial_estados"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    solicitud_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("solicitudes.id"), nullable=False
    )
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False
    )
    estado_anterior: Mapped[EstadoSolicitud] = mapped_column(
        SAEnum(EstadoSolicitud, values_callable=lambda x: [e.value for e in x]),
        nullable=True
    )
    estado_nuevo: Mapped[EstadoSolicitud] = mapped_column(
        SAEnum(EstadoSolicitud, values_callable=lambda x: [e.value for e in x]),
        nullable=False
    )
    observacion: Mapped[str] = mapped_column(Text, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    solicitud: Mapped["Solicitud"] = relationship(
        "Solicitud", back_populates="historial"
    )
    usuario: Mapped["Usuario"] = relationship("Usuario", foreign_keys=[usuario_id])
