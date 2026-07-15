from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class ResolucionContador(Base):
    __tablename__ = "resolucion_contador"

    anio: Mapped[int] = mapped_column(Integer, primary_key=True)
    ultimo_numero: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
