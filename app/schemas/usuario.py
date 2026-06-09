import uuid
from pydantic import BaseModel, EmailStr
from datetime import datetime
from app.models.usuario import Rol


class UsuarioBase(BaseModel):
    nombre: str
    apellido: str
    email: EmailStr
    rol: Rol


class UsuarioCreate(UsuarioBase):
    password: str


class UsuarioResponse(UsuarioBase):
    id: uuid.UUID
    activo: bool
    creado_en: datetime

    model_config = {"from_attributes": True}


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    usuario: UsuarioResponse