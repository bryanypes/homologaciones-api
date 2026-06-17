import csv
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.catalogo import Pais, Departamento, Municipio
from app.models.academico import Institucion, Facultad, Programa
from app.models.usuario import Usuario, Rol
import bcrypt

async def crear_usuario_inicial(db: AsyncSession):
    # Verificar si el usuario existe
    result = await db.execute(select(Usuario).where(Usuario.email == "rector@universidad.edu.co"))
    if not result.scalar_one_or_none():
        password_hash = bcrypt.hashpw("Rector2024!".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        admin = Usuario(
            nombre="Rector",
            apellido="Universidad",
            email="rector@universidad.edu.co",
            password_hash=password_hash,
            rol=Rol.RECTOR,
            activo=True
        )
        db.add(admin)
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

    # Buscar municipio de Popayán
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

    for inst_idx, fac_idx, nombre, snies, tipo, metodologia in programas_data:
        db.add(Programa(
            nombre=nombre,
            codigo_snies=snies,
            tipo_formacion=tipo,
            metodologia=metodologia,
            institucion_id=instituciones_map[inst_idx],
            facultad_id=facultades_map[fac_idx] if fac_idx else None,
        ))

        