import base64
from pathlib import Path


def pdf_a_base64(ruta: str) -> str:
    with open(ruta, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def validar_ruta_pdf(ruta: str) -> Path:
    path = Path(ruta)
    if not path.exists():
        raise FileNotFoundError(f"Archivo no encontrado: {ruta}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"El archivo no es un PDF: {ruta}")
    return path