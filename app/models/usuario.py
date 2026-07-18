import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base
import enum

class Rol(str, enum.Enum):
    ADMIN = "admin"
    ESTUDIANTE = "estudiante"
    COORDINADOR = "coordinador"
    VICERRECTOR = "vicerrector"

class Usuario(Base):
    __tablename__ = "usuarios"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    apellido: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    cedula: Mapped[str] = mapped_column(String(20), unique=True, nullable=True, index=True)
    telefono: Mapped[str] = mapped_column(String(20), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    rol: Mapped[Rol] = mapped_column(SAEnum(Rol, name='rol', create_type=False, values_callable=lambda e: [m.value for m in e]), nullable=False, default=Rol.ESTUDIANTE)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    reset_token: Mapped[str] = mapped_column(String(255), nullable=True, unique=True, index=True)
    reset_token_expira: Mapped[datetime] = mapped_column(DateTime, nullable=True)