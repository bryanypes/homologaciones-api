"""
doc_service.py — Generación de Resolución de Homologación (CORREGIDA)

Estrategia: en lugar de construir el documento desde cero, tomamos la plantilla
oficial (proyeccion_RES_HOMOLOGACIÓN...) como base, desempaquetamos su XML,
reemplazamos los datos del estudiante/asignaturas, y volvemos a empaquetar.

CORRECCIÓN: Usa zipfile nativo en lugar de subprocess para empaquetar/desempaquetar.
Esto elimina la dependencia de scripts externos que no existen en Windows.
"""

import os
import re
import shutil
import zipfile
import tempfile
import uuid
import logging
from datetime import datetime
from typing import Optional
import sys

logger = logging.getLogger(__name__)

# Ruta a la plantilla oficial empacada — debe estar en el repo bajo templates/
PLANTILLA_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "templates", "resolucion_plantilla.docx")

MESES_ES = {
    1: "ENERO", 2: "FEBRERO", 3: "MARZO", 4: "ABRIL",
    5: "MAYO", 6: "JUNIO", 7: "JULIO", 8: "AGOSTO",
    9: "SEPTIEMBRE", 10: "OCTUBRE", 11: "NOVIEMBRE", 12: "DICIEMBRE",
}

SEMESTRE_ROMANO = {
    1: "I", 2: "II", 3: "III", 4: "IV", 5: "V",
    6: "VI", 7: "VII", 8: "VIII", 9: "IX", 10: "X",
}


def _unpack_docx(docx_path: str, output_dir: str) -> None:
    """Desempaqueta un DOCX (ZIP) a un directorio."""
    os.makedirs(output_dir, exist_ok=True)
    with zipfile.ZipFile(docx_path, 'r') as z:
        z.extractall(output_dir)


def _pack_docx(unpacked_dir: str, output_docx: str) -> None:
    """Empaqueta un directorio desempaquetado de vuelta a DOCX (ZIP)."""
    os.makedirs(os.path.dirname(output_docx), exist_ok=True)
    with zipfile.ZipFile(output_docx, 'w', zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(unpacked_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, unpacked_dir)
                z.write(file_path, arcname)


def _esc(text: str) -> str:
    """Escapa caracteres especiales XML."""
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def _run(tag: str, text: str, bold: bool = False, color: str = "", size: int = 0,
         font: str = "Arial Narrow") -> str:
    """Genera un <w:r> con su texto."""
    rpr_parts = [f'<w:rFonts w:ascii="{font}" w:hAnsi="{font}" w:cs="Arial"/>']
    if bold:
        rpr_parts.append("<w:b/>")
    if color:
        rpr_parts.append(f'<w:color w:val="{color}"/>')
    if size:
        rpr_parts.append(f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>')
    rpr = "<w:rPr>" + "".join(rpr_parts) + "</w:rPr>"
    space = ' xml:space="preserve"' if " " in text else ""
    return f"<w:r>{rpr}<w:t{space}>{_esc(text)}</w:t></w:r>"


def _par(content: str, style: str = "Normal", spacing_before: int = 0,
         spacing_after: int = 100, align: str = "") -> str:
    """Genera un <w:p> completo."""
    ppr_parts = [f'<w:pStyle w:val="{style}"/>']
    if spacing_before or spacing_after != 100:
        ppr_parts.append(f'<w:spacing w:before="{spacing_before}" w:after="{spacing_after}"/>')
    if align:
        ppr_parts.append(f'<w:jc w:val="{align}"/>')
    ppr = "<w:pPr>" + "".join(ppr_parts) + "</w:pPr>"
    return f"<w:p>{ppr}{content}</w:p>"


def _cell(text: str, bold: bool = False, bgcolor: str = "", width: int = 0,
          color_txt: str = "", align: str = "", size: int = 18) -> str:
    """Genera una celda de tabla."""
    rpr = f'<w:rFonts w:ascii="Arial Narrow" w:hAnsi="Arial Narrow" w:cs="Arial"/>'
    if bold:
        rpr += "<w:b/>"
    if color_txt:
        rpr += f'<w:color w:val="{color_txt}"/>'
    rpr += f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>'

    jc = f'<w:jc w:val="{align}"/>' if align else ""
    ppr = f'<w:pPr><w:spacing w:before="40" w:after="40"/>{jc}</w:pPr>'
    space = ' xml:space="preserve"' if " " in str(text) or not str(text) else ""
    cell_content = f'{ppr}<w:r><w:rPr>{rpr}</w:rPr><w:t{space}>{_esc(str(text))}</w:t></w:r>'

    shading = f'<w:shd w:val="clear" w:color="auto" w:fill="{bgcolor}"/>' if bgcolor else ""
    borders = """<w:tcBorders>
      <w:top w:val="single" w:sz="4" w:space="0" w:color="000000"/>
      <w:left w:val="single" w:sz="4" w:space="0" w:color="000000"/>
      <w:bottom w:val="single" w:sz="4" w:space="0" w:color="000000"/>
      <w:right w:val="single" w:sz="4" w:space="0" w:color="000000"/>
    </w:tcBorders>"""
    width_attr = f'<w:tcW w:w="{width}" w:type="dxa"/>' if width else ""
    margins = '<w:tcMar><w:top w:w="80" w:type="dxa"/><w:left w:w="108" w:type="dxa"/><w:bottom w:w="80" w:type="dxa"/><w:right w:w="108" w:type="dxa"/></w:tcMar>'
    tcp = f"<w:tcPr>{width_attr}{borders}{shading}{margins}</w:tcPr>"
    return f"<w:tc>{tcp}<w:p>{cell_content}</w:p></w:tc>"


def _tabla_homologadas(asignaturas: list, prog_origen: str, inst_origen: str) -> str:
    """
    Tabla principal: CURSOS ACADÉMICOS HOMOLOGADOS
    Columnas: Curso origen | Código | Curso Autónoma | Semestre | Créditos | IH | TP | Calificación
    """
    # Anchos en DXA para 9360 total (A4 con márgenes)
    W = [2200, 1000, 1600, 600, 700, 500, 500, 660]
    total_w = sum(W)
    col_widths = " ".join(str(w) for w in W)

    def header_row() -> str:
        headers = [
            ("CURSO INSTITUCIÓN DE ORIGEN", W[0]),
            ("CÓDIGO CURSO UNIAUTONOMA",    W[1]),
            ("CURSO ACADÉMICO AUTÓNOMA",    W[2]),
            ("SEMESTRE",                    W[3]),
            ("CRÉDITOS",                    W[4]),
            ("IH",                          W[5]),
            ("TP",                          W[6]),
            ("Calif",                       W[7]),
        ]
        cells = "".join(_cell(h, bold=True, bgcolor="1F3864", color_txt="FFFFFF", width=w, align="center") for h, w in headers)
        return f"<w:tr>{cells}</w:tr>"

    def meta_rows() -> str:
        def merge_row(label: str, value: str) -> str:
            c1 = _cell(label, bold=True, bgcolor="1F3864", color_txt="FFFFFF", width=W[0])
            # merge 7 columnas para el valor
            span = f"<w:tcPr><w:tcW w:w='{sum(W[1:])}' w:type='dxa'/><w:gridSpan w:val='7'/></w:tcPr>"
            p = f"<w:p><w:pPr><w:spacing w:before='40' w:after='40'/></w:pPr><w:r><w:rPr><w:rFonts w:ascii='Arial Narrow' w:hAnsi='Arial Narrow' w:cs='Arial'/><w:b/><w:color w:val='FFFFFF'/><w:sz w:val='18'/><w:szCs w:val='18'/></w:rPr><w:t xml:space='preserve'>{_esc(value)}</w:t></w:r></w:p>"
            c2 = f"<w:tc>{span}{p}</w:tc>"
            return f"<w:tr>{c1}{c2}</w:tr>"

        r1 = merge_row("PROGRAMA DE ORIGEN:", prog_origen.upper())
        r2 = merge_row("INSTITUCIÓN DE ORIGEN:", inst_origen.upper())
        r3_cells = f"""<w:tc><w:tcPr><w:tcW w:w='{total_w}' w:type='dxa'/><w:gridSpan w:val='8'/><w:shd w:val='clear' w:color='auto' w:fill='1F3864'/></w:tcPr>
          <w:p><w:pPr><w:jc w:val='center'/><w:spacing w:before='40' w:after='40'/></w:pPr>
          <w:r><w:rPr><w:rFonts w:ascii='Arial Narrow' w:hAnsi='Arial Narrow' w:cs='Arial'/><w:b/><w:color w:val='FFFFFF'/><w:sz w:val='18'/><w:szCs w:val='18'/></w:rPr><w:t>CURSOS ACADÉMICOS HOMOLOGADOS</w:t></w:r></w:p></w:tc>"""
        r3 = f"<w:tr>{r3_cells}</w:tr>"
        return r3 + r1 + r2

    def data_rows() -> str:
        rows = ""
        fill = "F2F2F2"
        for i, a in enumerate(asignaturas):
            bg = "" if i % 2 == 0 else fill
            sem = SEMESTRE_ROMANO.get(a.get("semestre_destino", 0), str(a.get("semestre_destino", "")))
            calif = str(a.get("calificacion_origen", "")).replace(".", ",") if a.get("calificacion_origen") else ""
            cells = (
                _cell(a.get("asignatura_origen", ""), width=W[0], bgcolor=bg) +
                _cell(str(a.get("codigo_destino", "")), width=W[1], bgcolor=bg, align="center") +
                _cell(a.get("asignatura_destino", ""), width=W[2], bgcolor=bg) +
                _cell(sem, width=W[3], bgcolor=bg, align="center") +
                _cell(str(a.get("creditos_destino", "")), width=W[4], bgcolor=bg, align="center") +
                _cell(str(a.get("intensidad_horaria_destino", "") or ""), width=W[5], bgcolor=bg, align="center") +
                _cell(a.get("tipo_destino", "") or "", width=W[6], bgcolor=bg, align="center") +
                _cell(calif, width=W[7], bgcolor=bg, align="center")
            )
            rows += f"<w:tr>{cells}</w:tr>"
        return rows

    def totals_row() -> str:
        total_cr = sum(a.get("creditos_destino", 0) or 0 for a in asignaturas)
        total_n = len(asignaturas)

        def span_cell(label: str, val, span: int, w_total: int) -> str:
            p = f"<w:p><w:pPr><w:spacing w:before='40' w:after='40'/></w:pPr><w:r><w:rPr><w:rFonts w:ascii='Arial Narrow' w:hAnsi='Arial Narrow' w:cs='Arial'/><w:b/><w:sz w:val='18'/><w:szCs w:val='18'/></w:rPr><w:t xml:space='preserve'>{_esc(label)}</w:t></w:r><w:r><w:rPr><w:rFonts w:ascii='Arial Narrow' w:hAnsi='Arial Narrow' w:cs='Arial'/><w:b/><w:sz w:val='18'/><w:szCs w:val='18'/></w:rPr><w:t xml:space='preserve'> {val}</w:t></w:r></w:p>"
            return f"<w:tc><w:tcPr><w:tcW w:w='{w_total}' w:type='dxa'/><w:gridSpan w:val='{span}'/></w:tcPr>{p}</w:tc>"

        c1 = span_cell("TOTAL, CURSOS HOMOLOGADOS:", total_n, 4, sum(W[:4]))
        c2 = span_cell("TOTAL, CRÉDITOS HOMOLOGADOS:", total_cr, 4, sum(W[4:]))
        return f"<w:tr>{c1}{c2}</w:tr>"

    table = f"""<w:tbl>
      <w:tblPr>
        <w:tblStyle w:val="Tablaconestilo1"/>
        <w:tblW w:w="{total_w}" w:type="dxa"/>
        <w:tblBorders>
          <w:insideH w:val="single" w:sz="4" w:space="0" w:color="000000"/>
          <w:insideV w:val="single" w:sz="4" w:space="0" w:color="000000"/>
        </w:tblBorders>
        <w:tblLook w:val="04A0"/>
      </w:tblPr>
      <w:tblGrid>{" ".join(f'<w:gridCol w:w="{w}"/>' for w in W)}</w:tblGrid>
      {meta_rows()}
      {header_row()}
      {data_rows()}
      {totals_row()}
    </w:tbl>"""
    return table


def _tabla_cursos_pendientes(cursos_pendientes: list) -> str:
    """
    Tabla ARTÍCULO 2: Plan de estudios con cursos pendientes agrupados por semestre.
    """
    W = [500, 1000, 4500, 600, 600, 600, 1560]
    total_w = sum(W)

    def titulo_semestre(nombre: str) -> str:
        cells = "".join([
            _cell("No.", bold=True, bgcolor="1F3864", color_txt="FFFFFF", width=W[0], align="center"),
            _cell("Códigos", bold=True, bgcolor="1F3864", color_txt="FFFFFF", width=W[1], align="center"),
            _cell(nombre, bold=True, bgcolor="1F3864", color_txt="FFFFFF", width=W[2]),
            _cell("CR", bold=True, bgcolor="1F3864", color_txt="FFFFFF", width=W[3], align="center"),
            _cell("TP", bold=True, bgcolor="1F3864", color_txt="FFFFFF", width=W[4], align="center"),
            _cell("Tipo", bold=True, bgcolor="1F3864", color_txt="FFFFFF", width=W[5], align="center"),
            _cell("Línea de continuidad", bold=True, bgcolor="1F3864", color_txt="FFFFFF", width=W[6]),
        ])
        return f"<w:tr>{cells}</w:tr>"

    def total_row(cr: int, tp: int) -> str:
        label_cell = f"<w:tc><w:tcPr><w:tcW w:w='{sum(W[:3])}' w:type='dxa'/><w:gridSpan w:val='3'/></w:tcPr><w:p><w:pPr><w:spacing w:before='40' w:after='40'/></w:pPr><w:r><w:rPr><w:rFonts w:ascii='Arial Narrow' w:hAnsi='Arial Narrow' w:cs='Arial'/><w:b/><w:sz w:val='18'/><w:szCs w:val='18'/></w:rPr><w:t>Total Créditos Semestre</w:t></w:r></w:p></w:tc>"
        cr_cell = _cell(str(cr), bold=True, width=W[3], align="center")
        tp_cell = _cell(str(tp), bold=True, width=W[4], align="center")
        empty1  = _cell("", width=W[5])
        empty2  = _cell("", width=W[6])
        return f"<w:tr>{label_cell}{cr_cell}{tp_cell}{empty1}{empty2}</w:tr>"

    # Agrupar por semestre
    from collections import defaultdict
    semestres: dict = defaultdict(list)
    for c in cursos_pendientes:
        sem = c.get("semestre", 0)
        semestres[sem].append(c)

    rows = ""
    # Header global
    titulo_global = f"<w:tc><w:tcPr><w:tcW w:w='{total_w}' w:type='dxa'/><w:gridSpan w:val='7'/><w:shd w:val='clear' w:color='auto' w:fill='1F3864'/></w:tcPr><w:p><w:pPr><w:jc w:val='center'/><w:spacing w:before='40' w:after='40'/></w:pPr><w:r><w:rPr><w:rFonts w:ascii='Arial Narrow' w:hAnsi='Arial Narrow' w:cs='Arial'/><w:b/><w:color w:val='FFFFFF'/><w:sz w:val='18'/><w:szCs w:val='18'/></w:rPr><w:t>PLAN DE ESTUDIOS PROGRAMA INGENIERÍA DE SOFTWARE Y COMPUTACIÓN</w:t></w:r></w:p></w:tc>"
    rows += f"<w:tr>{titulo_global}</w:tr>"
    subtitulo = f"<w:tc><w:tcPr><w:tcW w:w='{total_w}' w:type='dxa'/><w:gridSpan w:val='7'/><w:shd w:val='clear' w:color='auto' w:fill='1F3864'/></w:tcPr><w:p><w:pPr><w:jc w:val='center'/><w:spacing w:before='40' w:after='40'/></w:pPr><w:r><w:rPr><w:rFonts w:ascii='Arial Narrow' w:hAnsi='Arial Narrow' w:cs='Arial'/><w:b/><w:color w:val='FFFFFF'/><w:sz w:val='18'/><w:szCs w:val='18'/></w:rPr><w:t>Aprobado en el Consejo Académico de Diciembre de 2019</w:t></w:r></w:p></w:tc>"
    rows += f"<w:tr>{subtitulo}</w:tr>"

    nombres_sem = {
        1: "PRIMER SEMESTRE", 2: "SEGUNDO SEMESTRE", 3: "TERCERO SEMESTRE",
        4: "CUARTO SEMESTRE", 5: "QUINTO SEMESTRE", 6: "SEXTO SEMESTRE",
        7: "SÉPTIMO SEMESTRE", 8: "OCTAVO SEMESTRE", 9: "NOVENO SEMESTRE",
        10: "DÉCIMO SEMESTRE",
    }

    for sem_num in sorted(semestres.keys()):
        cursos = semestres[sem_num]
        nom = nombres_sem.get(sem_num, f"SEMESTRE {sem_num}")
        rows += titulo_semestre(nom)
        total_cr = 0
        total_tp = 0
        for idx, c in enumerate(cursos, 1):
            cr = c.get("creditos", 0) or 0
            tp = c.get("tiempo_presencial", cr) or cr
            total_cr += cr
            total_tp += tp
            cells = (
                _cell(str(idx), width=W[0], align="center") +
                _cell(str(c.get("codigo", "")), width=W[1]) +
                _cell(c.get("nombre", ""), width=W[2]) +
                _cell(str(cr), width=W[3], align="center") +
                _cell(str(tp), width=W[4], align="center") +
                _cell(c.get("tipo", ""), width=W[5], align="center") +
                _cell(c.get("linea_continuidad", ""), width=W[6])
            )
            rows += f"<w:tr>{cells}</w:tr>"
        rows += total_row(total_cr, total_tp)

    return f"""<w:tbl>
      <w:tblPr>
        <w:tblW w:w="{total_w}" w:type="dxa"/>
        <w:tblBorders>
          <w:top w:val="single" w:sz="4" w:color="000000"/>
          <w:left w:val="single" w:sz="4" w:color="000000"/>
          <w:bottom w:val="single" w:sz="4" w:color="000000"/>
          <w:right w:val="single" w:sz="4" w:color="000000"/>
          <w:insideH w:val="single" w:sz="4" w:color="000000"/>
          <w:insideV w:val="single" w:sz="4" w:color="000000"/>
        </w:tblBorders>
      </w:tblPr>
      <w:tblGrid>{" ".join(f'<w:gridCol w:w="{w}"/>' for w in W)}</w:tblGrid>
      {rows}
    </w:tbl>"""


def _tabla_cursos_autorizar(cursos: list) -> str:
    """Tabla ARTÍCULO 3: Cursos autorizados para matrícula."""
    W = [400, 900, 3300, 900, 500, 500, 500, 1860]
    total_w = sum(W)
    headers = ["N°", "Código", "CURSO", "SEMESTRE", "CR", "IH", "TP", "Línea de Continuidad"]
    h_row = "".join(_cell(h, bold=True, bgcolor="1F3864", color_txt="FFFFFF", width=w, align="center")
                    for h, w in zip(headers, W))
    rows = f"<w:tr>{h_row}</w:tr>"
    total_cr = 0
    for i, c in enumerate(cursos, 1):
        cr = c.get("creditos", 0) or 0
        total_cr += cr
        sem = SEMESTRE_ROMANO.get(c.get("semestre", 0), "")
        bg = "" if i % 2 == 0 else "F2F2F2"
        cells = (
            _cell(str(i), width=W[0], bgcolor=bg, align="center") +
            _cell(str(c.get("codigo", "")), width=W[1], bgcolor=bg) +
            _cell(c.get("nombre", ""), width=W[2], bgcolor=bg) +
            _cell(sem, width=W[3], bgcolor=bg, align="center") +
            _cell(str(cr), width=W[4], bgcolor=bg, align="center") +
            _cell(str(c.get("ih", cr)), width=W[5], bgcolor=bg, align="center") +
            _cell(c.get("tipo", ""), width=W[6], bgcolor=bg, align="center") +
            _cell(c.get("linea", ""), width=W[7], bgcolor=bg)
        )
        rows += f"<w:tr>{cells}</w:tr>"

    # Totales
    def tot_row(label: str, val) -> str:
        span = sum(W[:-1])
        c1 = f"<w:tc><w:tcPr><w:tcW w:w='{span}' w:type='dxa'/><w:gridSpan w:val='7'/></w:tcPr><w:p><w:pPr><w:spacing w:before='40' w:after='40'/></w:pPr><w:r><w:rPr><w:rFonts w:ascii='Arial Narrow' w:hAnsi='Arial Narrow' w:cs='Arial'/><w:b/><w:sz w:val='18'/><w:szCs w:val='18'/></w:rPr><w:t xml:space='preserve'>{_esc(label)}</w:t></w:r></w:p></w:tc>"
        c2 = _cell(str(val), bold=True, width=W[-1], align="center")
        return f"<w:tr>{c1}{c2}</w:tr>"

    rows += tot_row("TOTAL CURSOS", len(cursos))
    rows += tot_row("TOTAL CREDITOS", total_cr)

    return f"""<w:tbl>
      <w:tblPr>
        <w:tblW w:w="{total_w}" w:type="dxa"/>
        <w:tblBorders>
          <w:top w:val="single" w:sz="4" w:color="000000"/>
          <w:left w:val="single" w:sz="4" w:color="000000"/>
          <w:bottom w:val="single" w:sz="4" w:color="000000"/>
          <w:right w:val="single" w:sz="4" w:color="000000"/>
          <w:insideH w:val="single" w:sz="4" w:color="000000"/>
          <w:insideV w:val="single" w:sz="4" w:color="000000"/>
        </w:tblBorders>
      </w:tblPr>
      <w:tblGrid>{" ".join(f'<w:gridCol w:w="{w}"/>' for w in W)}</w:tblGrid>
      {rows}
    </w:tbl>"""


def _tabla_folios(folios: dict) -> str:
    """Tabla de documentos analizados (Parágrafo 3 Art. 1)."""
    W = [7000, 1760]
    total_w = sum(W)
    header = f"<w:tr>{_cell('Documento', bold=True, bgcolor='1F3864', color_txt='FFFFFF', width=W[0])}{_cell('Número de Folios', bold=True, bgcolor='1F3864', color_txt='FFFFFF', width=W[1], align='center')}</w:tr>"
    docs = [
        ("Formato de solicitud del aspirante/estudiante.", folios.get("solicitud", 1)),
        ("Documento de aprobación legal del programa en la Institución de procedencia.", folios.get("aprobacion", 0)),
        ("Certificado oficial de calificaciones, en el cual deben figurar todas las asignaturas cursadas por estudiantes, la intensidad horaria total, los créditos y la calificación de cada una de ellas.", folios.get("calificaciones", 2)),
        ("Documento debidamente refrendado en donde conste el contenido programático de las asignaturas y aprobadas.", folios.get("contenido", 35)),
        ("Certificado oficial de buena conducta, expedido por la institución de procedencia.", folios.get("conducta", 0)),
    ]
    rows = header
    for i, (doc, n) in enumerate(docs):
        bg = "" if i % 2 == 0 else "F2F2F2"
        rows += f"<w:tr>{_cell(doc, width=W[0], bgcolor=bg)}{_cell(str(n), width=W[1], bgcolor=bg, align='center')}</w:tr>"
    total = sum(n for _, n in docs)
    rows += f"<w:tr>{_cell('TOTAL FOLIOS', bold=True, width=W[0])}{_cell(str(total), bold=True, width=W[1], align='center')}</w:tr>"
    return f"""<w:tbl>
      <w:tblPr><w:tblW w:w="{total_w}" w:type="dxa"/>
        <w:tblBorders><w:top w:val="single" w:sz="4" w:color="000000"/><w:left w:val="single" w:sz="4" w:color="000000"/><w:bottom w:val="single" w:sz="4" w:color="000000"/><w:right w:val="single" w:sz="4" w:color="000000"/><w:insideH w:val="single" w:sz="4" w:color="000000"/><w:insideV w:val="single" w:sz="4" w:color="000000"/></w:tblBorders>
      </w:tblPr>
      <w:tblGrid><w:gridCol w:w="{W[0]}"/><w:gridCol w:w="{W[1]}"/></w:tblGrid>
      {rows}
    </w:tbl>"""


def _obj_to_dict(obj) -> dict:
    """Convierte un objeto ORM o dict a diccionario de forma segura."""
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return {}


def _get_attr(obj, key: str, default=None):
    """Obtiene atributo de dict u objeto ORM de forma segura."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _build_document_xml(datos: dict) -> str:
    """
    Construye el XML completo de document.xml con toda la resolución.
    datos debe contener:
      - numero_resolucion: str
      - fecha_str: str  (ej. "16 DIC. 2024")
      - nombre_estudiante: str
      - cedula: str
      - ciudad_cedula: str
      - programa_origen: str
      - institucion_origen: str
      - correo: str (opcional)
      - telefono: str (opcional)
      - asignaturas: list de HomologacionAsignatura o dicts
      - cursos_pendientes: list  (calculado)
      - cursos_autorizar: list  (calculado)
      - periodo_autorizacion: str (ej. "primer período académico de 2025")
      - fecha_pago: str (opcional)
      - vicerrector: str
      - coordinador: str
      - fecha_notificacion: str
      - transcriptor: str
      - reviso: str
    """
    n = datos
    NR = n.get("numero_resolucion", "XXX")
    FECHA = n.get("fecha_str", "")
    NOMBRE = n.get("nombre_estudiante", "").upper()
    CC = n.get("cedula", "")
    CIUDAD = n.get("ciudad_cedula", "Popayán")
    PROG_ORIG = n.get("programa_origen", "")
    INST_ORIG = n.get("institucion_origen", "")
    PERIODO = n.get("periodo_autorizacion", "")
    VICERRECTOR = n.get("vicerrector", "SEBASTIÁN TORO VÉLEZ")
    COORDINADOR = n.get("coordinador", "JUAN PABLO DIAGO RODRÍGUEZ")
    FECHA_NOT = n.get("fecha_notificacion", FECHA)
    TRANSCRIPTOR = n.get("transcriptor", "")
    REVISO = n.get("reviso", "")

    # ✅ CORRECCIÓN: Convertir objetos ORM a dicts ANTES de usarlos
    asigs_raw = n.get("asignaturas", [])
    asigs = [_obj_to_dict(a) for a in asigs_raw]
    
    cursos_pend = n.get("cursos_pendientes", [])
    cursos_aut = n.get("cursos_autorizar", [])
    folios = n.get("folios", {})

    total_cursos = len(asigs)
    total_creditos = sum(a.get("creditos_destino", 0) or 0 for a in asigs)

    def p(text: str, bold_parts: list = None, indent: bool = False, align: str = "",
          spacing_b: int = 0, spacing_a: int = 100) -> str:
        """Párrafo de texto con soporte para partes en negrita."""
        ppr = '<w:pStyle w:val="Normal"/>'
        if indent:
            ppr += '<w:ind w:left="720"/>'
        if align:
            ppr += f'<w:jc w:val="{align}"/>'
        ppr += f'<w:spacing w:before="{spacing_b}" w:after="{spacing_a}"/>'
        ppr_block = f"<w:pPr>{ppr}</w:pPr>"

        if bold_parts is None:
            rpr = '<w:rPr><w:rFonts w:ascii="Arial Narrow" w:hAnsi="Arial Narrow" w:cs="Arial"/><w:sz w:val="20"/><w:szCs w:val="20"/></w:rPr>'
            space = ' xml:space="preserve"' if " " in text else ""
            content = f'<w:r>{rpr}<w:t{space}>{_esc(text)}</w:t></w:r>'
        else:
            content = ""
            for part, is_bold in bold_parts:
                b = "<w:b/>" if is_bold else ""
                rpr = f'<w:rPr><w:rFonts w:ascii="Arial Narrow" w:hAnsi="Arial Narrow" w:cs="Arial"/>{b}<w:sz w:val="20"/><w:szCs w:val="20"/></w:rPr>'
                space = ' xml:space="preserve"' if " " in part else ""
                content += f'<w:r>{rpr}<w:t{space}>{_esc(part)}</w:t></w:r>'
        return f"<w:p>{ppr_block}{content}</w:p>"

    def titulo(text: str, color: str = "0070C0") -> str:
        rpr = f'<w:rPr><w:rFonts w:ascii="Arial Narrow" w:hAnsi="Arial Narrow" w:cs="Arial"/><w:b/><w:color w:val="{color}"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr>'
        return f'<w:p><w:pPr><w:pStyle w:val="Normal"/><w:jc w:val="center"/><w:spacing w:before="100" w:after="100"/></w:pPr><w:r>{rpr}<w:t xml:space="preserve">{_esc(text)}</w:t></w:r></w:p>'

    def seccion(text: str) -> str:
        rpr = '<w:rPr><w:rFonts w:ascii="Arial Narrow" w:hAnsi="Arial Narrow" w:cs="Arial"/><w:b/><w:sz w:val="20"/><w:szCs w:val="20"/></w:rPr>'
        return f'<w:p><w:pPr><w:jc w:val="center"/><w:spacing w:before="160" w:after="80"/></w:pPr><w:r>{rpr}<w:t>{_esc(text)}</w:t></w:r></w:p>'

    def articulo(num: str, texto_parts: list) -> str:
        content = ""
        for part, bold in texto_parts:
            b = "<w:b/>" if bold else ""
            rpr = f'<w:rPr><w:rFonts w:ascii="Arial Narrow" w:hAnsi="Arial Narrow" w:cs="Arial"/>{b}<w:sz w:val="20"/><w:szCs w:val="20"/></w:rPr>'
            space = ' xml:space="preserve"' if " " in part else ""
            content += f'<w:r>{rpr}<w:t{space}>{_esc(part)}</w:t></w:r>'
        return f'<w:p><w:pPr><w:spacing w:before="160" w:after="80"/></w:pPr>{content}</w:p>'

    def paragrafo(num: str, texto: str) -> str:
        rpr_b = '<w:rPr><w:rFonts w:ascii="Arial Narrow" w:hAnsi="Arial Narrow" w:cs="Arial"/><w:b/><w:sz w:val="20"/><w:szCs w:val="20"/></w:rPr>'
        rpr_n = '<w:rPr><w:rFonts w:ascii="Arial Narrow" w:hAnsi="Arial Narrow" w:cs="Arial"/><w:sz w:val="20"/><w:szCs w:val="20"/></w:rPr>'
        return f'<w:p><w:pPr><w:spacing w:before="80" w:after="80"/></w:pPr><w:r>{rpr_b}<w:t xml:space="preserve">{_esc("Parágrafo " + num + ". ")}</w:t></w:r><w:r>{rpr_n}<w:t xml:space="preserve">{_esc(texto)}</w:t></w:r></w:p>'

    parts = []

    # ── Encabezado centrado ──────────────────────────────────────────────────
    parts.append(titulo(f"RESOLUCIÓN No. {NR}"))
    parts.append(titulo("Del"))
    parts.append(titulo(f"({FECHA})"))
    parts.append(p(""))

    # ── Considerando intro ───────────────────────────────────────────────────
    intro = (
        f"Por la cual se aprueba el estudio de homologación de los cursos aprobados en el {INST_ORIG.upper()}, "
        f"Programa de "
    )
    parts.append(p("", bold_parts=[
        (intro, False),
        (PROG_ORIG.upper(), True),
        (f", por el señor {NOMBRE}, identificado con la Cédula No. {CC} de {CIUDAD}.", False),
    ]))
    parts.append(p(""))
    parts.append(p(
        "El suscrito Vicerrector Académico de la CORPORACIÓN UNIVERSITARIA AUTÓNOMA DEL CAUCA, "
        "en uso de sus atribuciones reglamentarias y en especial las conferidas en el Acuerdo 010 de 2005 "
        "expedida por la ASAMBLEA DE FUNDADORES y el Reglamento Estudiantil Acuerdo 005 del 23 de julio de 2025. Artículo 57 y;"
    ))
    parts.append(p(""))
    parts.append(seccion("CONSIDERANDO"))
    parts.append(p(""))

    parts.append(p(
        f"Que la Coordinación del Programa de Ingeniería de Software y Computación realizó el estudio de "
        f"homologación de los cursos aprobados en la ({INST_ORIG.upper()}), por el señor {NOMBRE}, "
        f"identificado con cédula de ciudadanía No. {CC} de {CIUDAD}.",
        indent=False
    ))
    parts.append(p(""))
    parts.append(p(
        f"Que el Vicerrector Académico revisó los procedimientos aplicados y los anexos allegados por el señor "
        f"{NOMBRE} identificado con la Cédula No. {CC} de {CIUDAD}., para el estudio y análisis de la homologación "
        f"realizada por la Coordinación del Programa de Ingeniería de Software y Computación, con el correspondiente "
        f"pensum vigente del Programa de Ingeniería de Software y Computación aprobado mediante Resolución No. 15865 "
        f"del 18 de diciembre del 2019, y por lo anterior."
    ))
    parts.append(p(""))
    parts.append(seccion("RESUELVE"))
    parts.append(p(""))

    # ── ARTÍCULO 1 ───────────────────────────────────────────────────────────
    parts.append(articulo("1°", [
        ("ARTICULO 1°. ", True),
        (f"Aprobar el estudio de homologación del señor {NOMBRE} identificado con la Cédula No. {CC} de {CIUDAD}, de la siguiente manera: ", False),
    ]))
    parts.append(p("Entiéndase: CR: Crédito Académico, IH: Intensidad Horaria, TP: Tipo: T: Teórico, P: Práctico; TP: Teórico Práctico, NA: No Aplica."))
    parts.append(p(""))

    # Tabla homologadas — ya están convertidos a dicts arriba
    parts.append(_tabla_homologadas(asigs, PROG_ORIG, INST_ORIG))
    parts.append(p(""))

    # Parágrafo folios
    parts.append(p("", bold_parts=[
        ("Parágrafo 3. ", True),
        ("Para realizar este estudio se analizaron los siguientes documentos, los cuales reposarán en la hoja de vida del aspirante/estudiante:", False),
    ]))
    parts.append(_tabla_folios(folios))
    parts.append(p(""))

    # ── ARTÍCULO 2 ───────────────────────────────────────────────────────────
    parts.append(articulo("2°", [
        ("ARTICULO 2°. ", True),
        ("Definir los cursos pendientes por cursar y aprobar en la Corporación Universitaria Autónoma del Cauca así:", False),
    ]))
    parts.append(p(""))
    if cursos_pend:
        parts.append(_tabla_cursos_pendientes(cursos_pend))
    parts.append(p(""))

    parts.append(paragrafo(
        "1",
        "Se debe presentar como requisito de grado los siguientes certificados: 96 Horas de Seminario de Actualización, "
        "40 Horas de Curso de Extensión, Certificado de Actividad Deportivo Formativo y Suficiencia Internacional en Inglés."
    ))
    parts.append(p(""))

    # ── ARTÍCULO 3 ───────────────────────────────────────────────────────────
    parts.append(articulo("3°", [
        ("ARTICULO 3°. ", True),
        (f"Autorizar matricular para el {PERIODO} los siguientes cursos:", False),
    ]))
    parts.append(p(""))
    if cursos_aut:
        parts.append(_tabla_cursos_autorizar(cursos_aut))
    parts.append(p(""))

    parts.append(paragrafo(
        "1",
        "Para legalizar el proceso de matrícula tanto académica como financiera, deberá cancelar los derechos pecuniarios correspondientes."
    ))
    parts.append(p(""))
    parts.append(paragrafo(
        "2",
        "El aspirante/estudiante tendrá derecho a solicitar la revisión del estudio, para lo cual tendrá un plazo "
        "máximo de ocho días siguientes a su notificación, siempre y cuando esta revisión se refiera a la documentación "
        "entregada inicialmente. Cuando el aspirante/estudiante desee incorporar nuevos contenidos, se debe solicitar y "
        "realizar un nuevo estudio de homologación."
    ))
    parts.append(p(""))

    # ── ARTÍCULO 4 ───────────────────────────────────────────────────────────
    parts.append(articulo("4°", [
        ("ARTICULO 4°. ", True),
        ("  La presente resolución rige a partir de la fecha de su expedición.", False),
    ]))
    parts.append(p(""))
    parts.append(seccion("NOTIFIQUESE Y CUMPLASE"))
    parts.append(p(""))
    parts.append(p(f"Popayán, {FECHA}"))
    parts.append(p(""))
    parts.append(p(""))

    # Firmas (dos columnas con tabs)
    rpr_b = '<w:rPr><w:rFonts w:ascii="Arial Narrow" w:hAnsi="Arial Narrow" w:cs="Arial"/><w:b/><w:sz w:val="20"/><w:szCs w:val="20"/></w:rPr>'
    firma_row = f'<w:p><w:pPr><w:tabs><w:tab w:val="center" w:pos="4680"/></w:tabs><w:spacing w:before="80" w:after="40"/></w:pPr><w:r>{rpr_b}<w:t xml:space="preserve">{_esc(VICERRECTOR)}</w:t></w:r><w:r><w:rPr><w:tab/></w:rPr><w:tab/></w:r><w:r>{rpr_b}<w:t xml:space="preserve">{_esc(COORDINADOR)}</w:t></w:r></w:p>'
    cargo_row = f'<w:p><w:pPr><w:tabs><w:tab w:val="center" w:pos="4680"/></w:tabs><w:spacing w:before="40" w:after="80"/></w:pPr><w:r><w:rPr><w:rFonts w:ascii="Arial Narrow" w:hAnsi="Arial Narrow" w:cs="Arial"/><w:sz w:val="20"/><w:szCs w:val="20"/></w:rPr><w:t xml:space="preserve">Vicerrector Académico</w:t></w:r><w:r><w:rPr><w:tab/></w:rPr><w:tab/></w:r><w:r><w:rPr><w:rFonts w:ascii="Arial Narrow" w:hAnsi="Arial Narrow" w:cs="Arial"/><w:sz w:val="20"/><w:szCs w:val="20"/></w:rPr><w:t xml:space="preserve">Coordinador Programa de Ingeniería de Software</w:t></w:r></w:p>'
    parts.append(firma_row)
    parts.append(cargo_row)
    parts.append(p(""))

    # Notificado
    parts.append(p("Notificado (a): "))
    parts.append(p(""))
    parts.append(p(NOMBRE, bold_parts=[(NOMBRE, True)]))
    parts.append(p(f"Cédula de Ciudadanía No. {CC} de {CIUDAD}", bold_parts=[(f"Cédula de Ciudadanía No. {CC} de {CIUDAD}", True)]))
    parts.append(p(""))
    parts.append(p(f"Fecha de notificación: {FECHA_NOT}"))
    parts.append(p(""))
    parts.append(p("", bold_parts=[("Copia: ", False), ("\t\tVicerrectoría Académica", False)]))
    parts.append(p("\t\tOficina de Mercadeo y Admisiones"))
    parts.append(p("\t\tGestión Documental"))
    if TRANSCRIPTOR:
        parts.append(p("", bold_parts=[("Transcriptor:\t\t", False), (TRANSCRIPTOR, False)]))
    if REVISO:
        parts.append(p("", bold_parts=[("Revisó:\t\t", False), (REVISO, False)]))

    body_content = "\n".join(parts)

    # XML completo del documento manteniendo los namespaces del original
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas"
  xmlns:cx="http://schemas.microsoft.com/office/drawing/2014/chartex"
  xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
  xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"
  xmlns:v="urn:schemas-microsoft-com:vml"
  xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
  xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
  xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"
  xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml"
  mc:Ignorable="w14 w15">
  <w:body>
    {body_content}
    <w:sectPr>
      <w:headerReference w:type="default" r:id="rId1"/>
      <w:footerReference w:type="default" r:id="rId2"/>
      <w:pgSz w:w="12240" w:h="15840"/>
      <w:pgMar w:top="1134" w:right="1134" w:bottom="1701" w:left="1134" w:header="708" w:footer="708" w:gutter="0"/>
    </w:sectPr>
  </w:body>
</w:document>'''


def generar_resolucion_docx(homologacion, solicitud) -> str:
    """
    Punto de entrada principal. Recibe los modelos ORM y genera el .docx.
    Retorna la ruta al archivo generado.
    
    CORREGIDO: Usa zipfile en lugar de subprocess para empaquetar/desempaquetar.
    """
    import tempfile
    import shutil

    # Crear directorio de trabajo temporal
    tmpdir = tempfile.mkdtemp(prefix="homolog_")
    unpacked_dir = os.path.join(tmpdir, "unpacked")

    try:
        # 1. Copiar y desempacar la plantilla oficial
        plantilla_src = PLANTILLA_PATH
        if not os.path.exists(plantilla_src):
            # Fallback: buscar en ubicaciones alternativas
            for alt in [
                "templates/resolucion_plantilla.docx",
                "/app/templates/resolucion_plantilla.docx",
            ]:
                if os.path.exists(alt):
                    plantilla_src = alt
                    break

        plantilla_copia = os.path.join(tmpdir, "plantilla.docx")
        shutil.copy2(plantilla_src, plantilla_copia)
        
        # ✅ CORRECCIÓN: Usar zipfile en lugar de subprocess
        _unpack_docx(plantilla_copia, unpacked_dir)

        # 2. Construir datos para el documento
        estudiante = solicitud.estudiante
        nombre_completo = f"{estudiante.nombre} {estudiante.apellido}".upper()

        # Fecha actual formateada
        hoy = datetime.now()
        fecha_str = f"{hoy.day} {MESES_ES[hoy.month]}. {hoy.year}"
        fecha_not = f"{hoy.day:02d}/{hoy.month:02d}/{hoy.year}"

        datos = {
            "numero_resolucion": solicitud.numero_resolucion or "____",
            "fecha_str": fecha_str,
            "nombre_estudiante": nombre_completo,
            "cedula": solicitud.cedula or "",
            "ciudad_cedula": "Popayán",
            "correo": getattr(estudiante, "email", ""),
            "telefono": solicitud.telefono or "",
            "programa_origen": solicitud.programa_origen or "",
            "institucion_origen": solicitud.institucion_origen or "",
            "programa_destino": solicitud.programa_destino or "",
            "institucion_destino": solicitud.institucion_destino or "",
            "asignaturas": homologacion.asignaturas,
            "cursos_pendientes": [],   # Se calcula abajo si hay datos
            "cursos_autorizar": [],    # Se calcula abajo si hay datos
            "periodo_autorizacion": f"segundo período académico del {hoy.year}",
            "folios": {"solicitud": 1, "aprobacion": 0, "calificaciones": 2, "contenido": 35, "conducta": 0},
            "vicerrector": "SEBASTIÁN TORO VÉLEZ",
            "coordinador": "JUAN PABLO DIAGO RODRÍGUEZ",
            "fecha_notificacion": fecha_not,
            "transcriptor": "",
            "reviso": "",
        }

        # 3. Reemplazar document.xml
        doc_xml = _build_document_xml(datos)
        doc_xml_path = os.path.join(unpacked_dir, "word", "document.xml")
        with open(doc_xml_path, "w", encoding="utf-8") as f:
            f.write(doc_xml)

        # 4. Empacar de vuelta
        output_dir = os.path.join("uploads", "resoluciones")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"resolucion_{solicitud.id}.docx")

        # ✅ CORRECCIÓN: Usar zipfile en lugar de subprocess
        _pack_docx(unpacked_dir, output_path)

        logger.info(f"Resolución generada: {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"Error generando resolución: {str(e)}", exc_info=True)
        raise
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


