from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from uuid import UUID
from datetime import datetime
from app.models.solicitud import EstadoSolicitud


class SolicitudCreate(BaseModel):
    """Crear solicitud con opción de elegir de catálogo o escribir texto libre"""
    # Datos personales del estudiante (capturados en la solicitud)
    cedula: Optional[str] = None
    telefono: Optional[str] = None
    correo_contacto: Optional[EmailStr] = None

    # Programa origen: elegir de catálogo O escribir texto libre
    programa_origen_id: Optional[UUID] = None  # Si se elige del catálogo
    institucion_origen_texto: Optional[str] = None  # Si es "Otra"
    programa_origen_texto: Optional[str] = None  # Si es "Otra"

    # Programa destino: elegir de catálogo O escribir texto libre
    programa_destino_id: Optional[UUID] = None  # Si se elige del catálogo
    institucion_destino_texto: Optional[str] = None  # Si es "Otra"
    programa_destino_texto: Optional[str] = None  # Si es "Otra"

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

    numero_resolucion: Optional[str] = None
    estado: EstadoSolicitud
    observaciones: Optional[str] = None
    creado_en: datetime
    actualizado_en: datetime

    model_config = {"from_attributes": True}


class CambiarEstadoRequest(BaseModel):
    observacion: Optional[str] = None


class HistorialEstadoResponse(BaseModel):
    id: UUID
    estado_anterior: Optional[EstadoSolicitud] = None
    estado_nuevo: EstadoSolicitud
    observacion: Optional[str] = None
    creado_en: datetime
    usuario_id: UUID
    usuario_nombre: Optional[str] = None

    model_config = {"from_attributes": True}