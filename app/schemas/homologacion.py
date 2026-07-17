import uuid
from pydantic import BaseModel, model_validator
from datetime import datetime
from typing import Optional, Any
from app.models.homologacion import EstadoAsignatura


class ActualizarAsignaturaRequest(BaseModel):
    estado: Optional[EstadoAsignatura] = None
    justificacion: Optional[str] = None
    asignatura_destino: Optional[str] = None
    creditos_destino: Optional[float] = None
    codigo_destino: Optional[str] = None
    semestre_destino: Optional[int] = None
    intensidad_horaria_destino: Optional[int] = None
    tipo_destino: Optional[str] = None
    calificacion_origen: Optional[float] = None


class AgregarAsignaturaRequest(BaseModel):
    asignatura_origen: str
    creditos_origen: Optional[float] = None
    calificacion_origen: Optional[float] = None
    asignatura_destino: Optional[str] = None
    codigo_destino: Optional[str] = None
    semestre_destino: Optional[int] = None
    creditos_destino: Optional[float] = None
    intensidad_horaria_destino: Optional[int] = None
    tipo_destino: Optional[str] = None
    estado: EstadoAsignatura = EstadoAsignatura.HOMOLOGADA
    justificacion: Optional[str] = None
    similitud_porcentaje: Optional[float] = None


class HomologacionAsignaturaResponse(BaseModel):
    id: uuid.UUID
    asignatura_origen: str
    creditos_origen: Optional[float]
    calificacion_origen: Optional[float] = None
    asignatura_destino: Optional[str]
    codigo_destino: Optional[str] = None
    semestre_destino: Optional[int] = None
    creditos_destino: Optional[float]
    intensidad_horaria_destino: Optional[int] = None
    tipo_destino: Optional[str] = None
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
