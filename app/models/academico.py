import uuid
from sqlalchemy import String, ForeignKey, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class Institucion(Base):
    __tablename__ = "instituciones"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    codigo_ies: Mapped[str] = mapped_column(String(20), nullable=True)
    tipo: Mapped[str] = mapped_column(String(50), nullable=True)
    direccion: Mapped[str] = mapped_column(String(255), nullable=True)
    municipio_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("municipios.id"), nullable=True)

    municipio: Mapped["Municipio"] = relationship("Municipio")
    facultades: Mapped[list["Facultad"]] = relationship("Facultad", back_populates="institucion")


class Facultad(Base):
    __tablename__ = "facultades"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    institucion_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("instituciones.id"), nullable=False)

    institucion: Mapped["Institucion"] = relationship("Institucion", back_populates="facultades")
    programas: Mapped[list["Programa"]] = relationship("Programa", back_populates="facultad")


class Programa(Base):
    __tablename__ = "programas"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    codigo_snies: Mapped[str] = mapped_column(String(20), nullable=True)
    tipo_formacion: Mapped[str] = mapped_column(String(50), nullable=True)
    metodologia: Mapped[str] = mapped_column(String(50), nullable=True)
    descripcion: Mapped[str] = mapped_column(Text, nullable=True)
    facultad_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("facultades.id"), nullable=True)
    institucion_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("instituciones.id"), nullable=False)

    facultad: Mapped["Facultad"] = relationship("Facultad", back_populates="programas")
    institucion: Mapped["Institucion"] = relationship("Institucion")
    asignaturas: Mapped[list["Asignatura"]] = relationship("Asignatura", back_populates="programa")


class Asignatura(Base):
    __tablename__ = "asignaturas"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    creditos: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    programa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("programas.id"), nullable=False)
    codigo: Mapped[str] = mapped_column(String(50), nullable=True)
    semestre: Mapped[int] = mapped_column(Integer, nullable=True)
    tipo: Mapped[str] = mapped_column(String(10), nullable=True)
    intensidad_horaria: Mapped[int] = mapped_column(Integer, nullable=True)
    linea_continuidad: Mapped[str] = mapped_column(String(100), nullable=True)

    programa: Mapped["Programa"] = relationship("Programa", back_populates="asignaturas")