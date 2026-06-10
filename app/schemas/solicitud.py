import uuid
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from app.models.solicitud import EstadoSolicitud


class SolicitudCreate(BaseModel):
    programa_origen_id: Optional[uuid.UUID] = Field(None, description="ID del programa de origen del catálogo")
    programa_destino_id: Optional[uuid.UUID] = Field(None, description="ID del programa de destino del catálogo")
    institucion_origen: Optional[str] = Field(None, example="Universidad Nacional", description="Texto libre si no está en catálogo")
    programa_origen: Optional[str] = Field(None, example="Ingeniería de Sistemas", description="Texto libre si no está en catálogo")
    institucion_destino: Optional[str] = Field(None, example="Universidad del Cauca")
    programa_destino: Optional[str] = Field(None, example="Ingeniería en Electrónica")


class SolicitudResponse(BaseModel):
    id: uuid.UUID
    estudiante_id: uuid.UUID
    programa_origen_id: Optional[uuid.UUID]
    programa_destino_id: Optional[uuid.UUID]
    institucion_origen: Optional[str]
    programa_origen: Optional[str]
    institucion_destino: Optional[str]
    programa_destino: Optional[str]
    estado: EstadoSolicitud
    observaciones: Optional[str]
    creado_en: datetime
    actualizado_en: datetime

    model_config = {"from_attributes": True}


class CambiarEstadoRequest(BaseModel):
    observacion: Optional[str] = Field(None, example="Documentos revisados y completos")