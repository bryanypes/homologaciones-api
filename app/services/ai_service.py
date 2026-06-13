import json
import base64
from openai import AsyncOpenAI
from app.core.config import settings
from app.services.pdf_service import pdf_a_base64

client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

PROMPT_HOMOLOGACION = """
Eres un experto en homologaciones académicas universitarias colombianas con amplio conocimiento en normativa educativa del MEN (Ministerio de Educación Nacional).

Se te proporcionan dos documentos PDF:
1. **Certificado de calificaciones del estudiante** (institución de origen): contiene las asignaturas cursadas, intensidad horaria, créditos y calificaciones obtenidas.
2. **Pensum del programa destino** (institución receptora): contiene el plan de estudios completo con códigos, créditos, intensidad horaria y tipo de cada asignatura.

---

## CRITERIOS DE HOMOLOGACIÓN

Aplica estos criterios en orden de prioridad:

**1. Equivalencia temática (peso: 50%)**
Compara los contenidos programáticos implícitos en el nombre de cada asignatura de origen con las del destino. Una asignatura puede homologar a otra aunque el nombre sea diferente si los temas son equivalentes.

**2. Créditos y carga horaria (peso: 30%)**
- HOMOLOGADA: diferencia de créditos <= 1 crédito
- HOMOLOGADA_PARCIAL: diferencia de créditos entre 1 y 2 créditos
- NO_HOMOLOGADA: diferencia > 2 créditos o contenido incompatible

**3. Nivel de formación (peso: 20%)**
Un tecnólogo puede homologar hasta semestre 6 de un programa profesional de 9 semestres.

---

## REGLAS ESPECÍFICAS

- Una asignatura de origen puede homologar MÁXIMO UNA asignatura de destino.
- Una asignatura de destino puede ser homologada por MÁXIMO UNA de origen.
- Solo homologa si la calificación en origen es >= 3.0.
- Los créditos homologados deben reflejar los créditos de la asignatura DESTINO.
- Incluye TODAS las asignaturas del documento de origen en el array.

---

## FORMATO DE RESPUESTA

Responde ÚNICAMENTE con un objeto JSON válido, sin texto adicional, sin markdown, sin backticks:

{
  "resumen": "Texto ejecutivo de máximo 3 oraciones.",
  "programa_origen": "Nombre exacto del programa de origen",
  "institucion_origen": "Nombre exacto de la institución de origen",
  "programa_destino": "Nombre exacto del programa de destino",
  "institucion_destino": "Nombre exacto de la institución de destino",
  "total_creditos_homologados": 0,
  "total_asignaturas_homologadas": 0,
  "asignaturas": [
    {
      "asignatura_origen": "Nombre exacto de la asignatura en el documento de origen",
      "creditos_origen": 3,
      "calificacion_origen": 4.5,
      "asignatura_destino": "Nombre exacto de la asignatura en el pensum destino",
      "codigo_destino": "12190103",
      "semestre_destino": "I",
      "creditos_destino": 3,
      "intensidad_horaria_destino": 3,
      "tipo_destino": "TP",
      "estado": "homologada",
      "justificacion": "Justificación académica concisa de máximo 2 oraciones.",
      "similitud_porcentaje": 85.0
    }
  ]
}

Los valores válidos para estado son exactamente: homologada, no_homologada, homologada_parcial.
"""


async def subir_pdf(pdf_b64: str, nombre: str) -> str:
    """Sube un PDF al File API de OpenAI y retorna el file_id."""
    pdf_bytes = base64.b64decode(pdf_b64)
    response = await client.files.create(
        file=(nombre, pdf_bytes, "application/pdf"),
        purpose="assistants",
    )
    return response.id


async def eliminar_archivo(file_id: str):
    try:
        await client.files.delete(file_id)
    except Exception:
        pass


async def procesar_homologacion(ruta_origen: str, ruta_destino: str) -> dict:
    pdf_origen_b64 = pdf_a_base64(ruta_origen)
    pdf_destino_b64 = pdf_a_base64(ruta_destino)

    # Subir ambos PDFs al File API
    file_id_origen = await subir_pdf(pdf_origen_b64, "origen.pdf")
    file_id_destino = await subir_pdf(pdf_destino_b64, "destino.pdf")

    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Documento 1 - Certificado de calificaciones (origen):"
                        },
                        {
                            "type": "file",
                            "file": {"file_id": file_id_origen}
                        },
                        {
                            "type": "text",
                            "text": "Documento 2 - Pensum del programa destino:"
                        },
                        {
                            "type": "file",
                            "file": {"file_id": file_id_destino}
                        },
                        {
                            "type": "text",
                            "text": PROMPT_HOMOLOGACION
                        }
                    ]
                }
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
    finally:
        # Limpiar archivos subidos
        await eliminar_archivo(file_id_origen)
        await eliminar_archivo(file_id_destino)

    texto = response.choices[0].message.content.strip()
    resultado = json.loads(texto)
    resultado["tokens_utilizados"] = response.usage.total_tokens if response.usage else 0
    return resultado
    pdf_origen_b64 = pdf_a_base64(ruta_origen)
    pdf_destino_b64 = pdf_a_base64(ruta_destino)

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Documento 1 - Certificado de calificaciones (origen):"
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:application/pdf;base64,{pdf_origen_b64}"
                        }
                    },
                    {
                        "type": "text",
                        "text": "Documento 2 - Pensum del programa destino:"
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:application/pdf;base64,{pdf_destino_b64}"
                        }
                    },
                    {
                        "type": "text",
                        "text": PROMPT_HOMOLOGACION
                    }
                ]
            }
        ],
        response_format={"type": "json_object"},  # Garantiza JSON válido
        temperature=0,
    )

    texto = response.choices[0].message.content.strip()
    resultado = json.loads(texto)

    resultado["tokens_utilizados"] = response.usage.total_tokens if response.usage else 0
    return resultado