import uuid
from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from app.models.homologacion import EstadoAsignatura


class HomologacionAsignaturaResponse(BaseModel):
    id: uuid.UUID
    asignatura_origen: str
    creditos_origen: Optional[float]
    asignatura_destino: Optional[str]
    creditos_destino: Optional[float]
    estado: EstadoAsignatura
    justificacion: Optional[str]
    similitud_porcentaje: Optional[float]

    model_config = {"from_attributes": True}


class HomologacionResponse(BaseModel):
    id: uuid.UUID
    solicitud_id: uuid.UUID
    resumen_ia: Optional[str]
    tokens_utilizados: Optional[int]
    asignaturas: list[HomologacionAsignaturaResponse]
    creado_en: datetime

    model_config = {"from_attributes": True}