import uuid
from pydantic import BaseModel, Field
from typing import Optional


class InstitucionCreate(BaseModel):
    nombre: str = Field(..., example="Universidad del Cauca")
    direccion: Optional[str] = Field(None, example="Calle 5 # 4-70")
    municipio_id: Optional[uuid.UUID] = None


class InstitucionResponse(BaseModel):
    id: uuid.UUID
    nombre: str
    codigo_ies: Optional[str]
    tipo: Optional[str]
    direccion: Optional[str]
    municipio_id: Optional[uuid.UUID]

    model_config = {"from_attributes": True}


class FacultadCreate(BaseModel):
    nombre: str = Field(..., example="Facultad de Ingeniería Electrónica y Telecomunicaciones")
    institucion_id: uuid.UUID


class FacultadResponse(BaseModel):
    id: uuid.UUID
    nombre: str
    institucion_id: uuid.UUID

    model_config = {"from_attributes": True}


class ProgramaCreate(BaseModel):
    nombre: str = Field(..., example="Ingeniería de Sistemas")
    codigo_snies: Optional[str] = Field(None, example="1050")
    tipo_formacion: Optional[str] = Field(None, example="Profesional")
    metodologia: Optional[str] = Field(None, example="Presencial")
    descripcion: Optional[str] = None
    facultad_id: Optional[uuid.UUID] = None
    institucion_id: uuid.UUID


class ProgramaResponse(BaseModel):
    id: uuid.UUID
    nombre: str
    codigo_snies: Optional[str]
    tipo_formacion: Optional[str]
    metodologia: Optional[str]
    descripcion: Optional[str]
    facultad_id: Optional[uuid.UUID]
    institucion_id: uuid.UUID

    model_config = {"from_attributes": True}


class AsignaturaCreate(BaseModel):
    nombre: str = Field(..., example="Cálculo Diferencial")
    creditos: int = Field(..., example=3, ge=1, le=10)
    programa_id: uuid.UUID


class AsignaturaResponse(BaseModel):
    id: uuid.UUID
    nombre: str
    creditos: int
    programa_id: uuid.UUID

    model_config = {"from_attributes": True}