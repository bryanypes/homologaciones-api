import uuid
from pydantic import BaseModel, Field


class PaisResponse(BaseModel):
    id: uuid.UUID
    nombre: str
    codigo: str

    model_config = {"from_attributes": True}


class DepartamentoResponse(BaseModel):
    id: uuid.UUID
    nombre: str
    pais_id: uuid.UUID

    model_config = {"from_attributes": True}


class MunicipioResponse(BaseModel):
    id: uuid.UUID
    nombre: str
    departamento_id: uuid.UUID

    model_config = {"from_attributes": True}