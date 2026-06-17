from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from uuid import UUID
from datetime import datetime
from app.models.solicitud import EstadoSolicitud


class SolicitudCreate(BaseModel):
    # Datos personales del estudiante (capturados en la solicitud)
    cedula: Optional[str] = None
    telefono: Optional[str] = None
    correo_contacto: Optional[EmailStr] = None

    # Programa origen (texto libre o FK)
    institucion_origen: Optional[str] = None
    programa_origen: Optional[str] = None
    programa_origen_id: Optional[UUID] = None

    # Programa destino (texto libre o FK)
    institucion_destino: Optional[str] = None
    programa_destino: Optional[str] = None
    programa_destino_id: Optional[UUID] = None

    @field_validator("cedula")
    @classmethod
    def cedula_solo_numeros(cls, v):
        if v and not v.replace(" ", "").isdigit():
            raise ValueError("La cédula debe contener solo números")
        return v


class SolicitudResponse(BaseModel):
    id: UUID
    estudiante_id: UUID

    cedula: Optional[str] = None
    telefono: Optional[str] = None
    correo_contacto: Optional[str] = None

    institucion_origen: Optional[str] = None
    programa_origen: Optional[str] = None
    institucion_destino: Optional[str] = None
    programa_destino: Optional[str] = None
    programa_origen_id: Optional[UUID] = None
    programa_destino_id: Optional[UUID] = None

    estado: EstadoSolicitud
    observaciones: Optional[str] = None
    creado_en: datetime
    actualizado_en: datetime

    model_config = {"from_attributes": True}


class CambiarEstadoRequest(BaseModel):
    observacion: Optional[str] = None