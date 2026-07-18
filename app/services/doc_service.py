"""
doc_service.py — Generación de Resolución de Homologación con docxtpl

Usa la plantilla templates/plantilla_resolucion_matricula.docx (Jinja2).
"""

import os
import logging
from datetime import datetime

from docxtpl import DocxTemplate

logger = logging.getLogger(__name__)

PLANTILLA_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "templates", "plantilla_resolucion_matricula.docx")
)

MESES_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}

SEMESTRE_ROMANO = {
    1: "I", 2: "II", 3: "III", 4: "IV", 5: "V",
    6: "VI", 7: "VII", 8: "VIII", 9: "IX", 10: "X",
}

DOCUMENTOS_FOLIOS = [
    {"nombre": "Formato de solicitud del aspirante/estudiante.", "folios": 1},
    {
        "nombre": "Documento de aprobación legal del programa en la Institución de procedencia.",
        "folios": 0,
    },
    {
        "nombre": (
            "Certificado oficial de calificaciones, en el cual deben figurar todas las asignaturas "
            "cursadas por estudiantes, la intensidad horaria total, los créditos y la calificación "
            "de cada una de ellas."
        ),
        "folios": 2,
    },
    {
        "nombre": "Documento debidamente refrendado en donde conste el contenido programático de las asignaturas aprobadas.",
        "folios": 35,
    },
    {
        "nombre": "Certificado oficial de buena conducta, expedido por la institución de procedencia.",
        "folios": 0,
    },
]


def _sem_romano(n) -> str:
    try:
        return SEMESTRE_ROMANO.get(int(n), str(n))
    except (TypeError, ValueError):
        return str(n) if n else ""


def _safe_int(val) -> int:
    try:
        return int(val or 0)
    except (TypeError, ValueError):
        return 0


def _plantilla_path() -> str:
    for path in [
        PLANTILLA_PATH,
        "templates/plantilla_resolucion_matricula.docx",
        "/app/templates/plantilla_resolucion_matricula.docx",
    ]:
        if os.path.exists(path):
            return path
    raise FileNotFoundError(
        f"Plantilla no encontrada. Se buscó en: {PLANTILLA_PATH}"
    )


def generar_resolucion_docx(homologacion, solicitud, asignaturas_destino=None) -> str:
    """
    Genera la resolución Word usando docxtpl.
    Retorna la ruta local al archivo .docx generado.
    """
    estudiante = solicitud.estudiante
    nombre_completo = f"{estudiante.nombre} {estudiante.apellido}".upper()

    hoy = datetime.now()
    fecha_larga = f"{hoy.day} de {MESES_ES[hoy.month]} de {hoy.year}"
    fecha_notificacion = f"{hoy.day:02d}/{hoy.month:02d}/{hoy.year}"

    # ── Cursos homologados → bloque 1 ─────────────────────────────────────────
    cursos_bloque1 = []
    total_creditos_bloque1 = 0

    for a in homologacion.asignaturas:
        cr = _safe_int(getattr(a, "creditos_destino", None))
        total_creditos_bloque1 += cr
        calif_raw = getattr(a, "calificacion_origen", None)
        calif = str(calif_raw).replace(".", ",") if calif_raw is not None else ""
        cursos_bloque1.append({
            "origen":      getattr(a, "asignatura_origen", "") or "",
            "codigo":      str(getattr(a, "codigo_destino", "") or ""),
            "destino":     getattr(a, "asignatura_destino", "") or "",
            "semestre":    _sem_romano(getattr(a, "semestre_destino", None)),
            "cr":          str(cr) if cr else "",
            "ih":          str(getattr(a, "intensidad_horaria_destino", "") or ""),
            "tipo":        getattr(a, "tipo_destino", "") or "",
            "calificacion": calif,
        })

    # ── Bloque 2 vacío (un solo origen en la solicitud actual) ───────────────
    cursos_bloque2: list = []

    # ── Cursos proyectados (semestre más bajo pendiente, sem 1-9) ─────────────
    cursos_proyectados = []
    if asignaturas_destino:
        nombres_homologados = {
            (getattr(a, "asignatura_destino", "") or "").strip().lower()
            for a in homologacion.asignaturas
            if getattr(a, "estado", None) and a.estado.value == "homologada"
        }
        codigos_homologados = {
            (getattr(a, "codigo_destino", "") or "").strip()
            for a in homologacion.asignaturas
            if getattr(a, "estado", None) and a.estado.value == "homologada" and a.codigo_destino
        }

        pendientes = [
            a for a in asignaturas_destino
            if 0 < _safe_int(getattr(a, "semestre", None)) <= 9
            and (getattr(a, "nombre", "") or "").strip().lower() not in nombres_homologados
            and (getattr(a, "codigo", "") or "").strip() not in codigos_homologados
        ]
        pendientes.sort(key=lambda x: (_safe_int(getattr(x, "semestre", 99)), getattr(x, "nombre", "")))

        if pendientes:
            sem_min = _safe_int(getattr(pendientes[0], "semestre", 1))
            for a in pendientes:
                if _safe_int(getattr(a, "semestre", None)) != sem_min:
                    break
                cr = _safe_int(getattr(a, "creditos", None))
                cursos_proyectados.append({
                    "codigo":   getattr(a, "codigo", "") or "",
                    "curso":    getattr(a, "nombre", "") or "",
                    "semestre": _sem_romano(getattr(a, "semestre", None)),
                    "cr":       str(cr) if cr else "",
                    "ih":       str(getattr(a, "intensidad_horaria", None) or cr or ""),
                    "tipo":     getattr(a, "tipo", "") or "",
                })

    total_creditos_proyectados = sum(
        _safe_int(c["cr"]) for c in cursos_proyectados
    )

    # ── Documentos analizados ─────────────────────────────────────────────────
    documentos_anexos = list(DOCUMENTOS_FOLIOS)
    total_folios = sum(d["folios"] for d in documentos_anexos)

    # ── Contexto Jinja2 ───────────────────────────────────────────────────────
    context = {
        "numero_resolucion":        solicitud.numero_resolucion or "____",
        "fecha_resolucion":         fecha_larga,
        "fecha_firma":              fecha_larga,
        "fecha_notificacion":       fecha_notificacion,
        "nombre_revisor":           "JUAN PABLO DIAGO RODRÍGUEZ",
        "nombre_estudiante":        nombre_completo,
        "cedula":                   solicitud.cedula or "",
        "ciudad":                   "Popayán",
        "bloque1_programa_origen":  (solicitud.programa_origen or "").upper(),
        "bloque1_institucion_origen": (solicitud.institucion_origen or "").upper(),
        "bloque2_programa_origen":  "",
        "bloque2_institucion_origen": "",
        "cursos_bloque1":           cursos_bloque1,
        "total_cursos_bloque1":     len(cursos_bloque1),
        "total_creditos_bloque1":   total_creditos_bloque1,
        "cursos_bloque2":           cursos_bloque2,
        "total_cursos_bloque2":     0,
        "total_creditos_bloque2":   0,
        "documentos_anexos":        documentos_anexos,
        "total_folios":             total_folios,
        "cursos_proyectados":       cursos_proyectados,
        "total_cursos_proyectados": len(cursos_proyectados),
        "total_creditos_proyectados": total_creditos_proyectados,
    }

    tpl = DocxTemplate(_plantilla_path())
    tpl.render(context)

    output_dir = os.path.join("uploads", "resoluciones")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"resolucion_{solicitud.id}.docx")
    tpl.save(output_path)

    logger.info("Resolución generada: %s", output_path)
    return output_path
