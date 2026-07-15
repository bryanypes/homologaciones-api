import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base
import enum

class TipoDocumento(str, enum.Enum):
    PENSUM_ORIGEN = "pensum_origen"
    PENSUM_DESTINO = "pensum_destino"
    HOMOLOGACION_GENERADA = "homologacion_generada"
    RESOLUCION = "resolucion"

class Documento(Base):
    __tablename__ = "documentos"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    solicitud_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("solicitudes.id"), nullable=False, index=True)
    tipo: Mapped[TipoDocumento] = mapped_column(SAEnum(TipoDocumento, name='tipodocumento', create_type=False, values_callable=lambda e: [m.value for m in e]), nullable=False)
    nombre_original: Mapped[str] = mapped_column(String(255), nullable=False)
    ruta: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    tamano_bytes: Mapped[int] = mapped_column(nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    solicitud: Mapped["Solicitud"] = relationship("Solicitud", back_populates="documentos")
