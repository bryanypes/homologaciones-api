import uuid
from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class Pais(Base):
    __tablename__ = "paises"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    codigo: Mapped[str] = mapped_column(String(10), nullable=False, unique=True)

    departamentos: Mapped[list["Departamento"]] = relationship("Departamento", back_populates="pais")


class Departamento(Base):
    __tablename__ = "departamentos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    pais_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("paises.id"), nullable=False)

    pais: Mapped["Pais"] = relationship("Pais", back_populates="departamentos")
    municipios: Mapped[list["Municipio"]] = relationship("Municipio", back_populates="departamento")


class Municipio(Base):
    __tablename__ = "municipios"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    departamento_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("departamentos.id"), nullable=False)

    departamento: Mapped["Departamento"] = relationship("Departamento", back_populates="municipios")