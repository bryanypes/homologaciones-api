import uuid
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from app.models.usuario import Rol
from typing import Optional

class UsuarioBase(BaseModel):
    nombre: str = Field(..., example="Carlos", description="Nombre del usuario")
    apellido: str = Field(..., example="García", description="Apellido del usuario")
    email: EmailStr = Field(..., example="carlos@unicauca.edu.co", description="Correo institucional")
    rol: Rol = Field(..., example="estudiante", description="Rol: estudiante, coordinador o rector")


class UsuarioCreate(UsuarioBase):
    password: str = Field(..., example="123456", min_length=6, description="Contraseña mínimo 6 caracteres")


class UsuarioResponse(UsuarioBase):
    id: uuid.UUID
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
    password: Optional[str] = Field(None, example="nueva_clave", min_length=6, description="Nueva contraseña")
    rol: Optional[Rol] = Field(None, description="Nuevo rol")
    activo: Optional[bool] = Field(None, description="Activar o desactivar cuenta")


class UsuarioEditarPerfil(BaseModel):
    """Esquema para que el usuario edite su propio perfil"""
    nombre: Optional[str] = Field(None, example="Carlos", description="Nuevo nombre")
    apellido: Optional[str] = Field(None, example="García", description="Nuevo apellido")
    password_actual: Optional[str] = Field(None, description="Contraseña actual (requerida si cambias la contraseña)")
    password_nueva: Optional[str] = Field(None, example="nueva_clave", min_length=6, description="Nueva contraseña")


class SolicitarRecuperacionRequest(BaseModel):
    """Solicitar token para recuperar contraseña"""
    email: EmailStr = Field(..., example="carlos@unicauca.edu.co", description="Correo registrado")


class RestablecerContraseñaRequest(BaseModel):
    """Restablecer contraseña con token"""
    token: str = Field(..., description="Token de recuperación enviado al email")
    password_nueva: str = Field(..., min_length=6, description="Nueva contraseña")


class RecuperacionResponse(BaseModel):
    """Respuesta de solicitud de recuperación"""
    mensaje: str = Field(default="Se ha enviado un enlace de recuperación a tu correo")