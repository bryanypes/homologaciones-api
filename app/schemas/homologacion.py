import uuid
from pydantic import BaseModel, model_validator
from datetime import datetime
from typing import Optional, Any
from app.models.homologacion import EstadoAsignatura


class ActualizarAsignaturaRequest(BaseModel):
    estado: EstadoAsignatura
    justificacion: Optional[str] = None


class HomologacionAsignaturaResponse(BaseModel):
    id: uuid.UUID
    asignatura_origen: str
    creditos_origen: Optional[float]
    asignatura_destino: Optional[str]
    creditos_destino: Optional[float]
    estado: EstadoAsignatura
    estado_ia_original: Optional[EstadoAsignatura] = None
    fue_corregida: bool = False
    justificacion: Optional[str]
    similitud_porcentaje: Optional[float]

    model_config = {"from_attributes": True}


class HomologacionResponse(BaseModel):
    id: uuid.UUID
    solicitud_id: uuid.UUID
    nombre_estudiante: Optional[str] = None
    apellido_estudiante: Optional[str] = None
    resumen_ia: Optional[str]
    tokens_utilizados: Optional[int]
    asignaturas: list[HomologacionAsignaturaResponse]
    creado_en: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def _extraer_estudiante(cls, obj: Any) -> Any:
        if isinstance(obj, dict):
            return obj
        data = dict(obj.__dict__)
        data.pop("_sa_instance_state", None)
        solicitud = data.get("solicitud")
        if solicitud is not None:
            est = getattr(solicitud, "__dict__", {}).get("estudiante")
            if est is not None:
                data["nombre_estudiante"] = getattr(est, "nombre", None)
                data["apellido_estudiante"] = getattr(est, "apellido", None)
        return data