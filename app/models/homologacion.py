import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Text, Enum as SAEnum, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base
import enum


class EstadoAsignatura(str, enum.Enum):
    HOMOLOGADA = "homologada"
    NO_HOMOLOGADA = "no_homologada"
    HOMOLOGADA_PARCIAL = "homologada_parcial"


class Homologacion(Base):
    __tablename__ = "homologaciones"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    solicitud_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("solicitudes.id"), nullable=False, unique=True)
    documento_generado_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documentos.id"), nullable=True)
    resumen_ia: Mapped[str] = mapped_column(Text, nullable=True)
    tokens_utilizados: Mapped[int] = mapped_column(nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    solicitud: Mapped["Solicitud"] = relationship("Solicitud", back_populates="homologacion")
    documento_generado: Mapped["Documento"] = relationship("Documento", foreign_keys=[documento_generado_id])
    asignaturas: Mapped[list["HomologacionAsignatura"]] = relationship("HomologacionAsignatura", back_populates="homologacion")


class HomologacionAsignatura(Base):
    __tablename__ = "homologacion_asignaturas"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    homologacion_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("homologaciones.id"), nullable=False)
    asignatura_origen: Mapped[str] = mapped_column(String(255), nullable=False)
    creditos_origen: Mapped[float] = mapped_column(Float, nullable=True)
    asignatura_destino: Mapped[str] = mapped_column(String(255), nullable=True)
    creditos_destino: Mapped[float] = mapped_column(Float, nullable=True)
    estado: Mapped[EstadoAsignatura] = mapped_column(SAEnum(EstadoAsignatura), nullable=False)
    justificacion: Mapped[str] = mapped_column(Text, nullable=True)
    similitud_porcentaje: Mapped[float] = mapped_column(Float, nullable=True)

    homologacion: Mapped["Homologacion"] = relationship("Homologacion", back_populates="asignaturas")