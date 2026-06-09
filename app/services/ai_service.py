import anthropic
from app.core.config import settings
from app.services.pdf_service import pdf_a_base64

client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

PROMPT_HOMOLOGACION = """
Eres un experto en homologaciones académicas universitarias.

Se te proporcionan dos documentos:
1. Pensum de origen: materias cursadas por el estudiante en su institución de procedencia
2. Pensum de destino: materias del programa al que desea trasladarse

Tu tarea es:
1. Analizar ambos pensums
2. Identificar qué materias del pensum de origen pueden homologarse con materias del pensum de destino
3. Justificar cada homologación con criterios académicos claros (similitud de contenidos, créditos, nivel)
4. Identificar materias que NO pueden homologarse y por qué

Responde ÚNICAMENTE en el siguiente formato JSON, sin texto adicional:
{
  "resumen": "Resumen ejecutivo de la homologación",
  "asignaturas": [
    {
      "asignatura_origen": "Nombre de la materia de origen",
      "creditos_origen": 3,
      "asignatura_destino": "Nombre de la materia de destino",
      "creditos_destino": 3,
      "estado": "homologada|no_homologada|homologada_parcial",
      "justificacion": "Justificación académica",
      "similitud_porcentaje": 85.0
    }
  ]
}
"""


async def procesar_homologacion(ruta_origen: str, ruta_destino: str) -> dict:
    pdf_origen = pdf_a_base64(ruta_origen)
    pdf_destino = pdf_a_base64(ruta_destino)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_origen,
                        },
                        "title": "Pensum de origen",
                    },
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_destino,
                        },
                        "title": "Pensum de destino",
                    },
                    {
                        "type": "text",
                        "text": PROMPT_HOMOLOGACION,
                    },
                ],
            }
        ],
    )

    import json
    texto = response.content[0].text.strip()
    resultado = json.loads(texto)
    resultado["tokens_utilizados"] = response.usage.input_tokens + response.usage.output_tokens
    return resultado