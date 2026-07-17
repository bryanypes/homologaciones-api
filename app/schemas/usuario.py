import uuid
from pydantic import BaseModel, EmailStr, Field, field_validator
from datetime import datetime
from app.models.usuario import Rol
from typing import Optional


class UsuarioBase(BaseModel):
    nombre: str = Field(..., example="Carlos", description="Nombre del usuario")
    apellido: str = Field(..., example="García", description="Apellido del usuario")
    email: EmailStr = Field(..., example="carlos@unicauca.edu.co", description="Correo institucional")
    rol: Rol = Field(..., example="estudiante", description="Rol: estudiante, coordinador, vicerrector o admin")


class UsuarioCreate(UsuarioBase):
    password: str = Field(..., example="123456", min_length=6, description="Contraseña mínimo 6 caracteres")
    cedula: Optional[str] = Field(None, example="1061234567", description="Número de cédula (único en el sistema)")
    telefono: Optional[str] = Field(None, example="3001234567", description="Teléfono de contacto")

    @field_validator("cedula")
    @classmethod
    def cedula_solo_numeros(cls, v):
        if v and not v.replace(" ", "").isdigit():
            raise ValueError("La cédula debe contener solo números")
        return v


class UsuarioResponse(UsuarioBase):
    id: uuid.UUID
    cedula: Optional[str] = None
    telefono: Optional[str] = None
    activo: bool
    creado_en: datetime

    model_config = {"from_attributes": True}


class LoginRequest(BaseModel):
    email: EmailStr = Field(..., example="carlos@unicauca.edu.co")
    password: str = Field(..., example="123456")


class TokenResponse(BaseModel):
    access_token: str = Field(..., description="JWT para usar en Authorization header")
    token_type: str = Field(default="bearer")
    usuario: UsuarioResponse


class UsuarioUpdate(BaseModel):
    nombre: Optional[str] = Field(None, example="Carlos", description="Nuevo nombre")
    apellido: Optional[str] = Field(None, example="García", description="Nuevo apellido")
    cedula: Optional[str] = Field(None, example="1061234567", description="Número de cédula")
    telefono: Optional[str] = Field(None, example="3001234567", description="Teléfono")
    password: Optional[str] = Field(None, example="nueva_clave", min_length=6, description="Nueva contraseña")
    rol: Optional[Rol] = Field(None, description="Nuevo rol")
    activo: Optional[bool] = Field(None, description="Activar o desactivar cuenta")

    @field_validator("cedula")
    @classmethod
    def cedula_solo_numeros(cls, v):
        if v and not v.replace(" ", "").isdigit():
            raise ValueError("La cédula debe contener solo números")
        return v


class UsuarioEditarPerfil(BaseModel):
    nombre: Optional[str] = Field(None, example="Carlos", description="Nuevo nombre")
    apellido: Optional[str] = Field(None, example="García", description="Nuevo apellido")
    cedula: Optional[str] = Field(None, example="1061234567", description="Número de cédula")
    telefono: Optional[str] = Field(None, example="3001234567", description="Teléfono de contacto")
    password_actual: Optional[str] = Field(None, description="Contraseña actual (requerida si cambias la contraseña)")
    password_nueva: Optional[str] = Field(None, example="nueva_clave", min_length=6, description="Nueva contraseña")

    @field_validator("cedula")
    @classmethod
    def cedula_solo_numeros(cls, v):
        if v and not v.replace(" ", "").isdigit():
            raise ValueError("La cédula debe contener solo números")
        return v


class SolicitarRecuperacionRequest(BaseModel):
    email: EmailStr = Field(..., example="carlos@unicauca.edu.co", description="Correo registrado")


class RestablecerContraseñaRequest(BaseModel):
    token: str = Field(..., description="Token de recuperación enviado al email")
    password_nueva: str = Field(..., min_length=6, description="Nueva contraseña")


class RecuperacionResponse(BaseModel):
    mensaje: str = Field(default="Se ha enviado un enlace de recuperación a tu correo")
