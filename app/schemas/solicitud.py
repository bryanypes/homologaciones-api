import uuid
from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from app.models.solicitud import EstadoSolicitud


class SolicitudCreate(BaseModel):
    institucion_origen: str
    programa_origen: str
    institucion_destino: str
    programa_destino: str


class SolicitudResponse(BaseModel):
    id: uuid.UUID
    estudiante_id: uuid.UUID
    institucion_origen: str
    programa_origen: str
    institucion_destino: str
    programa_destino: str
    estado: EstadoSolicitud
    observaciones: Optional[str]
    creado_en: datetime
    actualizado_en: datetime

    model_config = {"from_attributes": True}


class CambiarEstadoRequest(BaseModel):
    observacion: Optional[str] = None