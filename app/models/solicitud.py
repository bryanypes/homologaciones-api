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

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    estudiante_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False)
    institucion_origen: Mapped[str] = mapped_column(String(255), nullable=False)
    programa_origen: Mapped[str] = mapped_column(String(255), nullable=False)
    institucion_destino: Mapped[str] = mapped_column(String(255), nullable=False)
    programa_destino: Mapped[str] = mapped_column(String(255), nullable=False)
    estado: Mapped[EstadoSolicitud] = mapped_column(SAEnum(EstadoSolicitud), default=EstadoSolicitud.BORRADOR)
    observaciones: Mapped[str] = mapped_column(Text, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    estudiante: Mapped["Usuario"] = relationship("Usuario", foreign_keys=[estudiante_id])
    documentos: Mapped[list["Documento"]] = relationship("Documento", back_populates="solicitud")
    homologacion: Mapped["Homologacion"] = relationship("Homologacion", back_populates="solicitud", uselist=False)
    historial: Mapped[list["HistorialEstado"]] = relationship("HistorialEstado", back_populates="solicitud")


class HistorialEstado(Base):
    __tablename__ = "historial_estados"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    solicitud_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("solicitudes.id"), nullable=False)
    usuario_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False)
    estado_anterior: Mapped[EstadoSolicitud] = mapped_column(SAEnum(EstadoSolicitud), nullable=True)
    estado_nuevo: Mapped[EstadoSolicitud] = mapped_column(SAEnum(EstadoSolicitud), nullable=False)
    observacion: Mapped[str] = mapped_column(Text, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    solicitud: Mapped["Solicitud"] = relationship("Solicitud", back_populates="historial")
    usuario: Mapped["Usuario"] = relationship("Usuario", foreign_keys=[usuario_id])