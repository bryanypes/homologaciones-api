"""
ai_service.py — Procesamiento de homologación con OpenAI GPT-4o-mini

Estrategia: extraer texto de los PDFs y enviarlo como texto plano.
GPT-4o-mini no acepta PDFs como imágenes — solo PNG/JPEG/WebP.
"""

import json
import logging
import re
from typing import Any

from openai import AsyncOpenAI
from app.core.config import settings

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


def _extraer_texto_pdf(ruta: str) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(ruta)
        paginas = []
        for i, page in enumerate(reader.pages):
            texto = page.extract_text()
            if texto and texto.strip():
                paginas.append(f"--- Página {i+1} ---\n{texto.strip()}")
        contenido = "\n\n".join(paginas)
        if not contenido.strip():
            raise ValueError("El PDF no contiene texto extraíble. Puede ser un PDF escaneado.")
        return contenido
    except ImportError:
        raise RuntimeError("pypdf no está instalado. Ejecuta: uv add pypdf")


SYSTEM_PROMPT = """Eres un experto en homologación académica universitaria colombiana, con amplio conocimiento del sistema de educación superior regulado por el Ministerio de Educación Nacional (MEN).

Tu tarea es analizar dos documentos académicos:
1. **Documento de origen**: certificado de calificaciones o hoja de vida académica del estudiante, que contiene las asignaturas cursadas, créditos y notas obtenidas en la institución de procedencia.
2. **Documento destino**: plan de estudios (pensum) del programa al que el estudiante desea trasladarse, que contiene las asignaturas, créditos, semestres e intensidad horaria del programa receptor.

Tu objetivo es determinar qué asignaturas del documento de origen son homologables con asignaturas del documento destino, y retornar un JSON estructurado con esa información.

## MARCO NORMATIVO APLICABLE

- Decreto 1295 de 2010 (MEN): un crédito académico equivale a 48 horas de trabajo del estudiante por período.
- Reglamento Estudiantil Uniautónoma del Cauca, Acuerdo 005 del 23 de julio de 2025, Artículo 57.
- Criterio general MEN: equivalencia temática mínima del 70% y diferencia de créditos no mayor al 25%.

## CRITERIOS DE HOMOLOGACIÓN

1. Contenido temático: similitud ≥ 70% con la asignatura destino.
2. Créditos: diferencia no mayor al 25% del valor destino.
3. Calificación aprobatoria: generalmente ≥ 3.0 sobre 5.0.
4. Nivel de complejidad coherente entre origen y destino.

## PRECEDENTES

SENA ADSO → Ing. Software (Res. 262/2024):
- "Analizar Requisitos Del Cliente..." → Introducción a la Programación (3cr, TP, 4.5)
- "Construir El Sistema..." → Bases de Datos I (4cr, TP, 4.5)
- "Aplicar Buenas Prácticas De Calidad..." → Ingeniería del Software I (4cr, TP, 4.5)

Ing. Mecánica UAO → Ing. Software (Res. 0251/2025):
- "MATEMATICAS FUNDAMENTALES" → Algebra Moderna (4cr, T, 3.6)
- "CÁLCULO I" → Cálculo I (3cr, T, 3.9)
- "ALGORITMIA Y PROGRAMACIÓN" → Introducción a la Programación (3cr, TP, 4.4)

## INSTRUCCIONES

1. Identifica todas las asignaturas del documento de origen con calificación y créditos.
2. Identifica todas las asignaturas del documento destino con código, semestre, créditos e intensidad horaria.
3. Evalúa equivalencias aplicando los criterios.
4. Incluye SOLO asignaturas con posibilidad real de homologación (HOMOLOGADA o PENDIENTE).
5. No inventes asignaturas que no estén en el documento destino.

## ESTADOS VÁLIDOS

- "HOMOLOGADA": cumple todos los criterios.
- "PENDIENTE": similitud limítrofe (60-70%), requiere revisión humana.
- "NO_HOMOLOGADA": no incluir en el resultado.

## FORMATO DE RESPUESTA

Responde ÚNICAMENTE con JSON válido. Sin markdown, sin texto antes ni después.

{
  "resumen": "Texto profesional 2-3 oraciones. Mencionar: institución y programa de origen, programa destino, total asignaturas y créditos. Tono formal universitario colombiano.",
  "tokens_utilizados": 0,
  "asignaturas": [
    {
      "asignatura_origen": "Nombre exacto del documento de origen",
      "creditos_origen": 3,
      "calificacion_origen": 4.5,
      "asignatura_destino": "Nombre exacto del documento destino",
      "codigo_destino": "12190103",
      "semestre_destino": 1,
      "creditos_destino": 3,
      "intensidad_horaria_destino": 3,
      "tipo_destino": "TP",
      "estado": "HOMOLOGADA",
      "justificacion": "Justificación técnica de 1-2 oraciones sobre la equivalencia.",
      "similitud_porcentaje": 85.0
    }
  ]
}

REGLAS: calificacion_origen es float o null. intensidad_horaria_destino es integer o null. tipo_destino es "T", "P", "TP" o null. similitud_porcentaje es número 0-100. codigo_destino es string o null.
"""


def _extraer_json(texto: str) -> dict:
    texto = re.sub(r"```(?:json)?", "", texto).strip().strip("`").strip()
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]+\}", texto)
        if match:
            return json.loads(match.group())
        raise ValueError(f"No se encontró JSON válido: {texto[:500]}")


async def procesar_homologacion(ruta_origen: str, ruta_destino: str) -> dict[str, Any]:
    client = _get_client()

    logger.info("[AI] Extrayendo texto de PDFs...")
    texto_origen = _extraer_texto_pdf(ruta_origen)
    texto_destino = _extraer_texto_pdf(ruta_destino)
    logger.info("[AI] Origen: %d chars — Destino: %d chars", len(texto_origen), len(texto_destino))

    MAX_CHARS = 40000
    if len(texto_origen) > MAX_CHARS:
        texto_origen = texto_origen[:MAX_CHARS] + "\n[... documento truncado ...]"
    if len(texto_destino) > MAX_CHARS:
        texto_destino = texto_destino[:MAX_CHARS] + "\n[... documento truncado ...]"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "DOCUMENTO 1 — Certificado de notas del estudiante (institución de origen):\n\n"
                f"{texto_origen}\n\n"
                "---\n\n"
                "DOCUMENTO 2 — Plan de estudios del programa destino:\n\n"
                f"{texto_destino}\n\n"
                "---\n\n"
                "Retorna ÚNICAMENTE el JSON de homologación. Sin texto adicional."
            )
        }
    ]

    logger.info("[AI] Enviando a GPT-4o-mini...")
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        max_tokens=4096,
        temperature=0.1,
    )

    raw = response.choices[0].message.content
    tokens = response.usage.total_tokens if response.usage else 0
    logger.info("[AI] Tokens usados: %d", tokens)

    resultado = _extraer_json(raw)
    resultado["tokens_utilizados"] = tokens

    if "asignaturas" not in resultado:
        raise ValueError("La respuesta de IA no contiene el campo 'asignaturas'")
    if not isinstance(resultado["asignaturas"], list):
        raise ValueError("El campo 'asignaturas' debe ser una lista")

    for asig in resultado["asignaturas"]:
        asig.setdefault("estado", "HOMOLOGADA")
        asig.setdefault("justificacion", "")
        asig.setdefault("similitud_porcentaje", None)
        asig.setdefault("calificacion_origen", None)
        asig.setdefault("creditos_origen", None)
        asig.setdefault("intensidad_horaria_destino", None)
        asig.setdefault("tipo_destino", None)
        asig.setdefault("codigo_destino", None)
        asig.setdefault("semestre_destino", None)

    logger.info("[AI] %d asignaturas identificadas", len(resultado["asignaturas"]))
    return resultado