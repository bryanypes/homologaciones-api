import os
import json
import subprocess
import tempfile
from pathlib import Path
from app.models.homologacion import (
    Homologacion,
    HomologacionAsignatura,
    EstadoAsignatura,
)


def generar_resolucion_docx(
    homologacion: Homologacion, solicitud, numero_resolucion: str = None
) -> str:
    """
    Genera el documento Word de resolución de homologación.
    Retorna la ruta del archivo generado.
    """
    from datetime import datetime

    numero = numero_resolucion or str(hash(str(homologacion.id)))[-4:]
    fecha = datetime.now().strftime("%d %b. %Y").upper()

    asignaturas_homologadas = [
        a
        for a in homologacion.asignaturas
        if a.estado
        in [EstadoAsignatura.HOMOLOGADA, EstadoAsignatura.HOMOLOGADA_PARCIAL]
    ]

    total_creditos = sum(a.creditos_destino or 0 for a in asignaturas_homologadas)

    data = {
        "numero_resolucion": numero,
        "fecha": fecha,
        "estudiante_nombre": f"{solicitud.estudiante.nombre} {solicitud.estudiante.apellido}".upper(),
        "estudiante_cedula": "___________",
        "ciudad_cedula": "Popayán",
        "programa_origen": solicitud.programa_origen or "Programa de Origen",
        "institucion_origen": solicitud.institucion_origen or "Institución de Origen",
        "programa_destino": solicitud.programa_destino or "Programa de Destino",
        "institucion_destino": "CORPORACIÓN UNIVERSITARIA AUTÓNOMA DEL CAUCA",
        "vicerrector": "VICERRECTOR ACADÉMICO",
        "coordinador": "COORDINADOR DE PROGRAMA",
        "cargo_coordinador": "Coordinador de Programa",
        "fecha_notificacion": datetime.now().strftime("%d-%m-%Y"),
        "periodo_matricula": "primer periodo académico",
        "plazo_matricula": "fecha límite de matrícula",
        "asignaturas_homologadas": [
            {
                "origen": a.asignatura_origen,
                "codigo": a.codigo_destino or "",
                "destino": a.asignatura_destino or "",
                "semestre": a.semestre_destino or "",
                "creditos": a.creditos_destino or 0,
                "ih": a.intensidad_horaria_destino or 0,
                "tipo": a.tipo_destino or "",
                "calif": str(a.calificacion_origen or ""),
            }
            for a in asignaturas_homologadas
        ],
        "total_cursos_homologados": len(asignaturas_homologadas),
        "total_creditos_homologados": int(total_creditos),
        "cursos_matricular": [],
        "total_cursos_matricular": 0,
        "total_creditos_matricular": 0,
        "folios": [
            {
                "documento": "Formato de solicitud del aspirante/estudiante.",
                "folios": 1,
            },
            {"documento": "Certificado oficial de calificaciones.", "folios": 2},
            {
                "documento": "Contenido programático de asignaturas aprobadas.",
                "folios": 35,
            },
        ],
        "total_folios": 38,
    }

    # Escribir script JS con los datos
    js_script = _build_js_script(data)

    with tempfile.TemporaryDirectory() as tmpdir:
        script_path = os.path.join(tmpdir, "gen.js")
        output_path = os.path.join(tmpdir, "resolucion.docx")

        with open(script_path, "w", encoding="utf-8") as f:
          safe_output_path = output_path.replace("\\", "\\\\")
          f.write(js_script.replace("OUTPUT_PATH", safe_output_path))

        result = subprocess.run(
            ["node", script_path],
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "NODE_PATH": str(Path(__file__).resolve().parents[2] / "node_modules"),
            },
        )

        if result.returncode != 0:
            raise Exception(f"Error generando documento: {result.stderr}")

        # Copiar a uploads
        os.makedirs("uploads/resoluciones", exist_ok=True)
        dest = f"uploads/resoluciones/resolucion_{homologacion.id}.docx"
        import shutil

        shutil.copy(output_path, dest)

    return dest


def _build_js_script(data: dict) -> str:
    data_json = json.dumps(data, ensure_ascii=False)
    return f"""
const {{
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, BorderStyle, WidthType, ShadingType, VerticalAlign
}} = require('docx');
const fs = require('fs');

const data = {data_json};

const border = {{ style: BorderStyle.SINGLE, size: 4, color: "000000" }};
const borders = {{ top: border, bottom: border, left: border, right: border }};
const noBorder = {{ style: BorderStyle.NONE, size: 0, color: "FFFFFF" }};
const noBorders = {{ top: noBorder, bottom: noBorder, left: noBorder, right: noBorder }};
const cellMargins = {{ top: 60, bottom: 60, left: 100, right: 100 }};

function boldText(text, size = 20) {{
  return new TextRun({{ text: String(text), bold: true, size, font: "Arial" }});
}}
function normalText(text, size = 20) {{
  return new TextRun({{ text: String(text), size, font: "Arial" }});
}}
function para(children, alignment = AlignmentType.LEFT) {{
  return new Paragraph({{ children, alignment, spacing: {{ before: 40, after: 40 }} }});
}}
function centerPara(children) {{
  return para(children, AlignmentType.CENTER);
}}
function headerCell(text, width) {{
  return new TableCell({{
    borders, width: {{ size: width, type: WidthType.DXA }},
    shading: {{ fill: "CCCCCC", type: ShadingType.CLEAR }},
    margins: cellMargins,
    children: [new Paragraph({{ children: [boldText(text, 18)], alignment: AlignmentType.CENTER }})]
  }});
}}
function dataCell(text, width, alignment = AlignmentType.LEFT) {{
  return new TableCell({{
    borders, width: {{ size: width, type: WidthType.DXA }},
    margins: cellMargins,
    children: [new Paragraph({{ children: [normalText(text, 18)], alignment }})]
  }});
}}

const colWidths = [2800, 1200, 2200, 600, 700, 500, 500, 700];
const totalW = colWidths.reduce((a,b) => a+b, 0);

const homologadasRows = [
  new TableRow({{ children: [
    new TableCell({{ borders, columnSpan: 2, width: {{ size: colWidths[0]+colWidths[1], type: WidthType.DXA }}, margins: cellMargins, shading: {{ fill: "CCCCCC", type: ShadingType.CLEAR }}, children: [new Paragraph({{ children: [boldText("PROGRAMA DE ORIGEN:", 18)] }})] }}),
    new TableCell({{ borders, columnSpan: 6, width: {{ size: totalW-colWidths[0]-colWidths[1], type: WidthType.DXA }}, margins: cellMargins, shading: {{ fill: "CCCCCC", type: ShadingType.CLEAR }}, children: [new Paragraph({{ children: [boldText(data.programa_origen, 18)] }})] }}),
  ]}}),
  new TableRow({{ children: [
    new TableCell({{ borders, columnSpan: 2, width: {{ size: colWidths[0]+colWidths[1], type: WidthType.DXA }}, margins: cellMargins, shading: {{ fill: "CCCCCC", type: ShadingType.CLEAR }}, children: [new Paragraph({{ children: [boldText("INSTITUCIÓN DE ORIGEN:", 18)] }})] }}),
    new TableCell({{ borders, columnSpan: 6, width: {{ size: totalW-colWidths[0]-colWidths[1], type: WidthType.DXA }}, margins: cellMargins, shading: {{ fill: "CCCCCC", type: ShadingType.CLEAR }}, children: [new Paragraph({{ children: [boldText(data.institucion_origen, 18)] }})] }}),
  ]}}),
  new TableRow({{ children: [
    new TableCell({{ borders, columnSpan: 8, width: {{ size: totalW, type: WidthType.DXA }}, margins: cellMargins, shading: {{ fill: "CCCCCC", type: ShadingType.CLEAR }}, children: [new Paragraph({{ children: [boldText("CURSOS ACADÉMICOS HOMOLOGADOS", 18)], alignment: AlignmentType.CENTER }})] }}),
  ]}}),
  new TableRow({{ children: [
    headerCell("CURSO INSTITUCIÓN DE ORIGEN", colWidths[0]),
    headerCell("CÓDIGO", colWidths[1]),
    headerCell("CURSO ACADÉMICO DESTINO", colWidths[2]),
    headerCell("SEM.", colWidths[3]),
    headerCell("CR.", colWidths[4]),
    headerCell("IH", colWidths[5]),
    headerCell("TP", colWidths[6]),
    headerCell("Calif.", colWidths[7]),
  ]}}),
  ...data.asignaturas_homologadas.map(a => new TableRow({{ children: [
    dataCell(a.origen, colWidths[0]),
    dataCell(a.codigo, colWidths[1], AlignmentType.CENTER),
    dataCell(a.destino, colWidths[2]),
    dataCell(a.semestre, colWidths[3], AlignmentType.CENTER),
    dataCell(String(a.creditos), colWidths[4], AlignmentType.CENTER),
    dataCell(String(a.ih), colWidths[5], AlignmentType.CENTER),
    dataCell(a.tipo, colWidths[6], AlignmentType.CENTER),
    dataCell(a.calif, colWidths[7], AlignmentType.CENTER),
  ]}})),
  new TableRow({{ children: [
    new TableCell({{ borders, columnSpan: 2, width: {{ size: colWidths[0]+colWidths[1], type: WidthType.DXA }}, margins: cellMargins, shading: {{ fill: "CCCCCC", type: ShadingType.CLEAR }}, children: [new Paragraph({{ children: [boldText("TOTAL CURSOS HOMOLOGADOS:", 18)] }})] }}),
    new TableCell({{ borders, columnSpan: 6, width: {{ size: totalW-colWidths[0]-colWidths[1], type: WidthType.DXA }}, margins: cellMargins, children: [new Paragraph({{ children: [boldText(String(data.total_cursos_homologados), 18)], alignment: AlignmentType.CENTER }})] }}),
  ]}}),
  new TableRow({{ children: [
    new TableCell({{ borders, columnSpan: 2, width: {{ size: colWidths[0]+colWidths[1], type: WidthType.DXA }}, margins: cellMargins, shading: {{ fill: "CCCCCC", type: ShadingType.CLEAR }}, children: [new Paragraph({{ children: [boldText("TOTAL CRÉDITOS HOMOLOGADOS:", 18)] }})] }}),
    new TableCell({{ borders, columnSpan: 6, width: {{ size: totalW-colWidths[0]-colWidths[1], type: WidthType.DXA }}, margins: cellMargins, children: [new Paragraph({{ children: [boldText(String(data.total_creditos_homologados), 18)], alignment: AlignmentType.CENTER }})] }}),
  ]}}),
];

const foliosTable = new Table({{
  width: {{ size: 9000, type: WidthType.DXA }},
  columnWidths: [6500, 2500],
  rows: [
    new TableRow({{ children: [headerCell("Documento", 6500), headerCell("Número de Folios", 2500)] }}),
    ...data.folios.map(f => new TableRow({{ children: [
      dataCell(f.documento, 6500),
      dataCell(String(f.folios), 2500, AlignmentType.CENTER),
    ]}})),
    new TableRow({{ children: [
      new TableCell({{ borders, width: {{ size: 6500, type: WidthType.DXA }}, margins: cellMargins, shading: {{ fill: "CCCCCC", type: ShadingType.CLEAR }}, children: [new Paragraph({{ children: [boldText("TOTAL FOLIOS", 18)], alignment: AlignmentType.RIGHT }})] }}),
      new TableCell({{ borders, width: {{ size: 2500, type: WidthType.DXA }}, margins: cellMargins, children: [new Paragraph({{ children: [boldText(String(data.total_folios), 18)], alignment: AlignmentType.CENTER }})] }}),
    ]}}),
  ]
}});

const doc = new Document({{
  sections: [{{
    properties: {{
      page: {{
        size: {{ width: 12240, height: 15840 }},
        margin: {{ top: 720, right: 1008, bottom: 720, left: 1008 }}
      }}
    }},
    children: [
      centerPara([boldText(`RESOLUCIÓN No. ${{data.numero_resolucion}}`, 22)]),
      centerPara([boldText(`Del (${{data.fecha}})`, 22)]),
      para([]),
      para([
        normalText("Por la cual se aprueba el estudio de homologación de los cursos aprobados en el "),
        boldText(data.institucion_origen),
        normalText(", Programa de "),
        boldText(data.programa_origen),
        normalText(`, por el señor ${{data.estudiante_nombre}} identificado con la Cédula No. ${{data.estudiante_cedula}} de ${{data.ciudad_cedula}}.`),
      ]),
      para([]),
      centerPara([boldText("CONSIDERANDO")]),
      para([]),
      para([normalText(`Que el estudio de homologación fue realizado para el Programa ${{data.programa_origen}}, en ${{data.institucion_origen}}, solicitado por el señor ${{data.estudiante_nombre}} identificado con la Cédula No. ${{data.estudiante_cedula}} de ${{data.ciudad_cedula}}.`)]),
      para([]),
      centerPara([boldText("RESUELVE")]),
      para([]),
      para([boldText("ARTÍCULO 1°. "), normalText(`Aprobar el estudio de homologación del señor ${{data.estudiante_nombre}} identificado con la Cédula No. ${{data.estudiante_cedula}} de ${{data.ciudad_cedula}}, de la siguiente manera:`)]),
      para([normalText("Entiéndase: CR: Crédito Académico, IH: Intensidad Horaria, TP: Tipo: T: Teórico, P: Práctico; TP: Teórico Práctico.")]),
      para([]),
      new Table({{ width: {{ size: totalW, type: WidthType.DXA }}, columnWidths: colWidths, rows: homologadasRows }}),
      para([]),
      para([boldText("ARTÍCULO 2°. "), normalText("Para realizar este estudio se analizaron los siguientes documentos:")]),
      foliosTable,
      para([]),
      para([boldText("ARTÍCULO 3°. "), normalText(`La presente resolución rige a partir de la fecha de su expedición.`)]),
      para([]),
      centerPara([boldText("NOTIFÍQUESE Y CÚMPLASE")]),
      para([]),
      centerPara([normalText(`Popayán, ${{data.fecha}}`)]),
      para([]),
      new Table({{
        width: {{ size: 9000, type: WidthType.DXA }},
        columnWidths: [4500, 4500],
        rows: [new TableRow({{ children: [
          new TableCell({{ borders: noBorders, width: {{ size: 4500, type: WidthType.DXA }}, margins: cellMargins, children: [
            new Paragraph({{ children: [boldText(data.vicerrector, 20)], alignment: AlignmentType.CENTER }}),
            new Paragraph({{ children: [normalText("Vicerrector Académico", 20)], alignment: AlignmentType.CENTER }}),
          ]}}),
          new TableCell({{ borders: noBorders, width: {{ size: 4500, type: WidthType.DXA }}, margins: cellMargins, children: [
            new Paragraph({{ children: [boldText(data.coordinador, 20)], alignment: AlignmentType.CENTER }}),
            new Paragraph({{ children: [normalText(data.cargo_coordinador, 20)], alignment: AlignmentType.CENTER }}),
          ]}}),
        ]}})]
      }}),
      para([]),
      para([boldText("Notificado (a): "), normalText(data.estudiante_nombre)]),
      para([boldText("Cédula: "), normalText(`${{data.estudiante_cedula}} de ${{data.ciudad_cedula}}`)]),
      para([boldText("Fecha de notificación: "), normalText(data.fecha_notificacion)]),
    ]
  }}]
}});

Packer.toBuffer(doc).then(buffer => {{
  fs.writeFileSync('OUTPUT_PATH', buffer);
  console.log('done');
}});
"""
