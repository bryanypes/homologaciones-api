from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID
from app.models.documento import TipoDocumento
from typing import Optional

class DocumentoResponse(BaseModel):
    id: UUID
    solicitud_id: UUID
    tipo: TipoDocumento
    nombre_original: str = Field(..., example="certificado_notas.pdf")
    mime_type: str = Field(..., example="application/pdf")
    tamano_bytes: int = Field(..., example=2048576)
    url: Optional[str] = Field(None, description="URL pública para descargar el documento")
    creado_en: datetime

    model_config = {"from_attributes": True}