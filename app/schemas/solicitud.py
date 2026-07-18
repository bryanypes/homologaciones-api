from pydantic import BaseModel, EmailStr, field_validator, model_validator
from typing import Optional, Any
from uuid import UUID
from datetime import datetime
from app.models.solicitud import EstadoSolicitud


class SolicitudCreate(BaseModel):
    cedula: Optional[str] = None
    telefono: Optional[str] = None
    correo_contacto: Optional[EmailStr] = None

    programa_origen_id: Optional[UUID] = None
    institucion_origen_texto: Optional[str] = None
    programa_origen_texto: Optional[str] = None

    programa_destino_id: Optional[UUID] = None
    institucion_destino_texto: Optional[str] = None
    programa_destino_texto: Optional[str] = None

    @field_validator("cedula")
    @classmethod
    def cedula_solo_numeros(cls, v):
        if v and not v.replace(" ", "").isdigit():
            raise ValueError("La cédula debe contener solo números")
        return v


class SolicitudResponse(BaseModel):
    id: UUID
    estudiante_id: UUID
    nombre_estudiante: Optional[str] = None
    apellido_estudiante: Optional[str] = None
    email_estudiante: Optional[str] = None

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

    @model_validator(mode="before")
    @classmethod
    def _extraer_estudiante(cls, obj: Any) -> Any:
        if isinstance(obj, dict):
            return obj
        data = dict(obj.__dict__)
        data.pop("_sa_instance_state", None)
        est = data.get("estudiante")
        if est is not None:
            data["nombre_estudiante"] = getattr(est, "nombre", None)
            data["apellido_estudiante"] = getattr(est, "apellido", None)
            data["email_estudiante"] = getattr(est, "email", None)
        return data


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