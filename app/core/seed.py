import csv
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.catalogo import Pais, Departamento, Municipio
from app.models.academico import Institucion, Facultad, Programa, Asignatura
from app.models.usuario import Usuario, Rol
import bcrypt

async def crear_usuario_inicial(db: AsyncSession):
    usuarios_iniciales = [
        {
            "nombre": "Admin",
            "apellido": "Sistema",
            "email": "admin@universidad.edu.co",
            "password": "Admin2024!",
            "rol": Rol.ADMIN,
        },
        {
            "nombre": "Vicerrector",
            "apellido": "Académico",
            "email": "vicerrector@universidad.edu.co",
            "password": "Rector2024!",
            "rol": Rol.VICERRECTOR,
        },
    ]
    for u in usuarios_iniciales:
        result = await db.execute(select(Usuario).where(Usuario.email == u["email"]))
        if not result.scalar_one_or_none():
            password_hash = bcrypt.hashpw(u["password"].encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            db.add(Usuario(
                nombre=u["nombre"],
                apellido=u["apellido"],
                email=u["email"],
                password_hash=password_hash,
                rol=u["rol"],
                activo=True,
            ))
    await db.commit()

DATA_DIR = Path(__file__).parent.parent.parent / "database" / "data"

CODIGOS_PAISES = {
    "Colombia": "CO",
    "Otro": "OT",
}


async def seed_catalogos(db: AsyncSession) -> None:
    result = await db.execute(select(Pais).limit(1))
    if result.scalar_one_or_none():
        return

    paises_map = {}
    with open(DATA_DIR / "paises.csv", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            pais = Pais(
                nombre=row["nombre"],
                codigo=CODIGOS_PAISES.get(row["nombre"], row["id_pais"]),
            )
            db.add(pais)
            await db.flush()
            paises_map[int(row["id_pais"])] = pais.id

    deptos_map = {}
    with open(DATA_DIR / "departamentos.csv", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            depto = Departamento(
                nombre=row["nombre"],
                pais_id=paises_map[int(row["pais_id"])],
            )
            db.add(depto)
            await db.flush()
            deptos_map[int(row["id_departamento"])] = depto.id

    with open(DATA_DIR / "municipios.csv", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            db.add(Municipio(
                nombre=row["nombre"],
                departamento_id=deptos_map[int(row["departamento_id"])],
            ))

    await db.flush()
    await seed_academico(db, deptos_map)
    await db.commit()
    await crear_usuario_inicial(db)


async def seed_academico(db: AsyncSession, deptos_map: dict) -> None:
    result = await db.execute(select(Institucion).limit(1))
    if result.scalar_one_or_none():
        return

    result = await db.execute(select(Municipio).where(Municipio.nombre == "Popayán"))
    popayan = result.scalar_one_or_none()
    popayan_id = popayan.id if popayan else None

    instituciones_data = [
        ("Corporación Universitaria Autónoma del Cauca", "2849", "Universitaria"),
        ("Servicio Nacional de Aprendizaje - SENA", None, "SENA"),
        ("Colegio Mayor del Cauca", "3104", "Mixta"),
        ("Fundación Universitaria de Popayán - FUP", "1055", "Mixta"),
        ("Universidad del Cauca", "1110", "Universitaria"),
    ]

    instituciones_map = {}
    for i, (nombre, codigo, tipo) in enumerate(instituciones_data, start=1):
        inst = Institucion(
            nombre=nombre,
            codigo_ies=codigo,
            tipo=tipo,
            municipio_id=popayan_id,
        )
        db.add(inst)
        await db.flush()
        instituciones_map[i] = inst.id

    facultades_data = [
        (5, "Facultad de Ingeniería Civil"),
        (5, "Facultad de Ingeniería Electrónica y Telecomunicaciones"),
        (4, "Facultad de Ingeniería y Arquitectura"),
        (3, "Facultad de Ingeniería"),
        (1, "Facultad de Ingeniería"),
    ]

    facultades_map = {}
    for i, (inst_idx, nombre) in enumerate(facultades_data, start=1):
        fac = Facultad(
            nombre=nombre,
            institucion_id=instituciones_map[inst_idx],
        )
        db.add(fac)
        await db.flush()
        facultades_map[i] = fac.id

    programas_data = [
        (5, 2, "Ingeniería Electrónica y Telecomunicaciones", "3104", "Profesional", "Presencial"),
        (5, 1, "Ingeniería Civil", "1105", "Profesional", "Presencial"),
        (5, 2, "Ingeniería de Sistemas", "1050", "Profesional", "Presencial"),
        (5, 2, "Ingeniería en Automática Industrial", "1106", "Profesional", "Presencial"),
        (5, 2, "Ingeniería Física", "1107", "Profesional", "Presencial"),
        (4, 3, "Ingeniería de Sistemas", "2612", "Profesional", "Presencial"),
        (4, 3, "Ingeniería Industrial", "2555", "Profesional", "Presencial"),
        (4, 3, "Arquitectura", "3615", "Profesional", "Presencial"),
        (3, 4, "Ingeniería Informática", "106716", "Profesional", "Presencial"),
        (3, 4, "Ingeniería Electrónica", "54559", "Profesional", "Presencial"),
        (3, 4, "Tecnología en Desarrollo de Software", "1108", "Tecnólogo", "Presencial"),
        (1, 5, "Ingeniería de Software y Computación", "110398", "Profesional", "Presencial"),
        (1, 5, "Ingeniería Electrónica", "20415", "Profesional", "Presencial"),
        (1, 5, "Ingeniería Civil", "111155", "Profesional", "Presencial"),
        (1, 5, "Ingeniería Energética", "110670", "Profesional", "Presencial"),
        (2, None, "Tecnólogo en Análisis y Desarrollo de Software", None, "Tecnólogo", "Presencial"),
        (2, None, "Técnico en Sistemas", None, "Técnico", "Presencial"),
        (2, None, "Tecnólogo en Gestión de Redes de Datos", None, "Tecnólogo", "Presencial"),
        (2, None, "Tecnólogo en Producción Multimedia", None, "Tecnólogo", "Presencial"),
        (2, None, "Técnico en Programación de Software", None, "Técnico", "Presencial"),
        (2, None, "Tecnólogo en Implementación de Infraestructura TIC", None, "Tecnólogo", "Presencial"),
        (2, None, "Tecnólogo en Gestión de la Seguridad y Salud en el Trabajo", None, "Tecnólogo", "Presencial"),
        (2, None, "Tecnólogo en Gestión de Proyectos de Desarrollo de Software", None, "Tecnólogo", "Presencial"),
    ]

    programas_map = {}
    for i, (inst_idx, fac_idx, nombre, snies, tipo, metodologia) in enumerate(programas_data, start=1):
        prog = Programa(
            nombre=nombre,
            codigo_snies=snies,
            tipo_formacion=tipo,
            metodologia=metodologia,
            institucion_id=instituciones_map[inst_idx],
            facultad_id=facultades_map[fac_idx] if fac_idx else None,
        )
        db.add(prog)
        await db.flush()
        programas_map[i] = prog.id

    # Pensum ISW y Computación (SNIES 110398) — programa índice 12
    await seed_asignaturas_isw(db, programas_map[12])


async def seed_asignaturas_isw(db: AsyncSession, programa_id) -> None:
    result = await db.execute(
        select(Asignatura).where(Asignatura.programa_id == programa_id).limit(1)
    )
    if result.scalar_one_or_none():
        return

    # (codigo, nombre, creditos, semestre, tipo, ih, linea_continuidad)
    # semestre 10 = Trabajo de Grado, semestre 11 = Requisitos de Grado
    asignaturas = [
        ("12190101", "Algebra Moderna",                                  4, 1, "T",  4, ""),
        ("12190102", "Introducción a la Ingeniería",                     2, 1, "T",  2, ""),
        ("12190103", "Introducción a la Programación",                   3, 1, "TP", 3, ""),
        ("12190104", "Cátedra Autónoma",                                 2, 1, "T",  2, ""),
        ("12190105", "Lectura y Escritura de Textos Académicos",         2, 1, "T",  2, ""),
        ("12190106", "Educación y Legislación Ambiental",                3, 1, "T",  2, ""),
        ("12190204", "Cálculo I",                                        3, 2, "T",  3, "Algebra Moderna"),
        ("12190205", "Álgebra Lineal",                                   2, 2, "T",  2, ""),
        ("12190206", "Física I",                                         3, 2, "TP", 3, ""),
        ("12190207", "Programación I",                                   4, 2, "TP", 4, ""),
        ("12190208", "Cultura Emprendedora",                             2, 2, "T",  2, ""),
        ("12190209", "Ambiente y Sociedad",                              3, 2, "T",  3, ""),
        ("12190210", "Competencias Ciudadanas",                          2, 2, "T",  2, ""),
        ("12190308", "Cálculo II",                                       3, 3, "T",  3, "Cálculo I"),
        ("12190309", "Matemáticas Discretas",                            3, 3, "T",  3, "Álgebra Lineal"),
        ("12190310", "Física II",                                        3, 3, "TP", 3, "Física I"),
        ("12190311", "Arquitectura de Computadores",                     3, 3, "TP", 3, ""),
        ("12190312", "Programación II",                                  4, 3, "TP", 4, ""),
        ("12190313", "Inglés I",                                         2, 3, "T",  2, ""),
        ("12190413", "Ecuaciones Diferenciales",                         3, 4, "T",  3, "Cálculo II"),
        ("12190414", "Bases de Datos I",                                 4, 4, "TP", 4, ""),
        ("12190415", "Estructura de Datos",                              4, 4, "TP", 4, ""),
        ("12190416", "Ingeniería del Software I",                        4, 4, "TP", 4, ""),
        ("12190417", "Inglés II",                                        2, 4, "T",  2, ""),
        ("12190418", "Transformación Digital e Innovación",              1, 4, "T",  1, ""),
        ("12190517", "Probabilidad Computacional y Estadística",         3, 5, "T",  3, ""),
        ("12190518", "Bases de Datos II",                                4, 5, "TP", 4, ""),
        ("12190519", "Complejidad Algorítmica",                          3, 5, "T",  4, ""),
        ("12190520", "Desarrollo de Aplicaciones Web",                   2, 5, "TP", 2, ""),
        ("12190521", "Ingeniería del Software II",                       4, 5, "T",  4, "Ingeniería del Software I"),
        ("12190522", "Inglés III",                                       2, 5, "T",  2, ""),
        ("12190622", "Análisis Numérico",                                3, 6, "T",  3, ""),
        ("12190623", "Arquitectura de Sistemas Operativos",              3, 6, "T",  3, ""),
        ("12190624", "Bases de Datos Avanzadas",                         2, 6, "TP", 2, "Bases de Datos II"),
        ("12190625", "Teoría de la Computación",                         3, 6, "T",  3, ""),
        ("12190626", "Desarrollo de Aplicaciones Móviles",               2, 6, "TP", 2, "Desarrollo de Aplicaciones Web"),
        ("12190627", "Calidad del Software I",                           3, 6, "T",  3, ""),
        ("12190628", "Inglés IV",                                        2, 6, "T",  2, ""),
        ("12190728", "Modelado para la Computación",                     3, 7, "T",  3, ""),
        ("12190729", "Redes de Computadores",                            2, 7, "TP", 2, ""),
        ("12190730", "Seguridad Informática",                            3, 7, "T",  3, ""),
        ("12190731", "Arquitectura de Software",                         3, 7, "TP", 3, "Desarrollo de Aplicaciones Móviles"),
        ("12190732", "Calidad del Software II",                          3, 7, "T",  3, "Calidad del Software I"),
        ("12190733", "Fundamentos y Metodología de la Investigación",    2, 7, "T",  2, ""),
        ("12190734", "Herramientas para Pensamiento Filosófico",         2, 7, "T",  2, ""),
        ("12190833", "Gestión de Redes",                                 2, 8, "TP", 2, "Redes de Computadores"),
        ("12190834", "Sistemas de Información Empresariales",            3, 8, "TP", 3, ""),
        ("12190835", "Electiva I",                                       2, 8, "TP", 2, ""),
        ("12190836", "Electiva III",                                     3, 8, "TP", 3, ""),
        ("12190837", "Electiva V",                                       3, 8, "TP", 3, ""),
        ("12190838", "Creatividad e Innovación",                         2, 8, "T",  2, ""),
        ("12190839", "Taller de Investigación",                          2, 8, "T",  2, "Fundamentos y Metodología de la Investigación"),
        ("12190938", "HCI",                                              2, 9, "TP", 2, ""),
        ("12190939", "Práctica Profesional",                             2, 9, "P",  2, ""),
        ("12190940", "Gestión Tecnológica y Financiera",                 2, 9, "T",  2, ""),
        ("12190941", "Electiva II",                                      2, 9, "T",  2, ""),
        ("12190942", "Electiva IV",                                      3, 9, "TP", 3, ""),
        ("12190943", "Electiva VI",                                      3, 9, "TP", 3, ""),
        ("12190944", "Inteligencia Social y Pensamiento Crítico (Sociología)", 2, 9, "T", 2, ""),
        ("TGRADO1219", "Trabajo de Grado Ing. De Software",             0, 10, "TP", 0, ""),
        ("12191102", "96 Horas de Seminario de Actualización",           0, 11, "TP", 0, ""),
        ("12191103", "40 Horas de Curso de Extensión",                   0, 11, "TP", 0, ""),
        ("12191104", "Cert. Actividad Dep. Formativo",                   0, 11, "TP", 0, ""),
        ("12191105", "Suficiencia Internacional Inglés",                  0, 11, "TP", 0, ""),
    ]

    for codigo, nombre, creditos, semestre, tipo, ih, linea in asignaturas:
        db.add(Asignatura(
            nombre=nombre,
            creditos=creditos,
            programa_id=programa_id,
            codigo=codigo,
            semestre=semestre,
            tipo=tipo,
            intensidad_horaria=ih,
            linea_continuidad=linea,
        ))

