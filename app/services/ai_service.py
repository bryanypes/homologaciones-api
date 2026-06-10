import anthropic
from app.core.config import settings
from app.services.pdf_service import pdf_a_base64

client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

PROMPT_HOMOLOGACION = """
Eres un experto en homologaciones académicas universitarias colombianas con amplio conocimiento en normativa educativa del MEN (Ministerio de Educación Nacional).

Se te proporcionan dos documentos PDF:
1. **Certificado de calificaciones del estudiante** (institución de origen): contiene las asignaturas cursadas, intensidad horaria, créditos y calificaciones obtenidas.
2. **Pensum del programa destino** (institución receptora): contiene el plan de estudios completo con códigos, créditos, intensidad horaria y tipo de cada asignatura.

---

## CRITERIOS DE HOMOLOGACIÓN

Aplica estos criterios en orden de prioridad:

**1. Equivalencia temática (peso: 50%)**
Compara los contenidos programáticos implícitos en el nombre de cada asignatura de origen con las del destino. Una asignatura puede homologar a otra aunque el nombre sea diferente si los temas son equivalentes (ej: "Analizar requisitos del cliente para construir sistemas de información" → "Introducción a la Programación").

**2. Créditos y carga horaria (peso: 30%)**
- HOMOLOGADA: diferencia de créditos ≤ 1 crédito
- HOMOLOGADA_PARCIAL: diferencia de créditos entre 1 y 2 créditos
- NO_HOMOLOGADA: diferencia > 2 créditos o contenido incompatible

**3. Nivel de formación (peso: 20%)**
Considera el nivel: Técnico < Tecnólogo < Profesional. Un tecnólogo puede homologar hasta semestre 6 de un programa profesional de 9 semestres. No homologues materias de ciclos avanzados (semestres 7-9) a partir de formación tecnológica salvo que haya evidencia clara de equivalencia.

---

## REGLAS ESPECÍFICAS

- Una asignatura de origen puede homologar MÁXIMO UNA asignatura de destino.
- Una asignatura de destino puede ser homologada por MÁXIMO UNA de origen.
- Si una asignatura de origen no tiene equivalente claro, marca estado "no_homologada" con justificación.
- Las asignaturas de formación humanística, ciudadana o de idiomas tienen alta probabilidad de homologación entre instituciones.
- Las asignaturas matemáticas y de ciencias básicas requieren alta similitud temática.
- Calificaciones mínimas: solo homologa si la calificación en origen es ≥ 3.0 (escala 0-5) o equivalente aprobatorio.
- Los créditos homologados deben reflejar los créditos de la asignatura DESTINO, no de origen.

---

## FORMATO DE RESPUESTA

Responde ÚNICAMENTE con un objeto JSON válido, sin texto adicional, sin markdown, sin backticks. Exactamente este esquema:

{
  "resumen": "Texto ejecutivo de máximo 3 oraciones explicando el resultado global de la homologación: cuántos créditos se homologan, de qué programa viene el estudiante, a cuál va, y una valoración general.",
  "programa_origen": "Nombre exacto del programa de origen según el documento",
  "institucion_origen": "Nombre exacto de la institución de origen",
  "programa_destino": "Nombre exacto del programa de destino según el documento",
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
      "justificacion": "Justificación académica concisa de máximo 2 oraciones explicando por qué se homologa o no.",
      "similitud_porcentaje": 85.0
    }
  ]
}

Los valores válidos para "estado" son exactamente: "homologada", "no_homologada", "homologada_parcial".
El campo "similitud_porcentaje" debe ser un número entre 0 y 100.
Incluye TODAS las asignaturas del documento de origen en el array, incluso las no homologadas.
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