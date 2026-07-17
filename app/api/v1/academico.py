from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from app.core.database import get_db
from app.core.deps import get_current_user, require_rol
from app.models.usuario import Rol
from app.models.academico import Institucion, Facultad, Programa, Asignatura
from app.schemas.academico import (
    InstitucionCreate, InstitucionResponse,
    FacultadCreate, FacultadResponse,
    ProgramaCreate, ProgramaResponse,
    AsignaturaCreate, AsignaturaResponse,
)

router = APIRouter(tags=["Académico"])


# --- Instituciones ---

@router.get(
    "/instituciones",
    response_model=list[InstitucionResponse],
    summary="Listar instituciones",
)
async def listar_instituciones(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    result = await db.execute(select(Institucion).order_by(Institucion.nombre))
    return result.scalars().all()


@router.post(
    "/instituciones",
    response_model=InstitucionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear institución",
    description="Solo coordinadores y rectores pueden crear instituciones.",
)
async def crear_institucion(
    data: InstitucionCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_rol(Rol.ADMIN)),
):
    institucion = Institucion(**data.model_dump())
    db.add(institucion)
    await db.commit()
    await db.refresh(institucion)
    return institucion


@router.get(
    "/instituciones/{institucion_id}",
    response_model=InstitucionResponse,
    summary="Obtener institución",
)
async def obtener_institucion(
    institucion_id: UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    result = await db.execute(select(Institucion).where(Institucion.id == institucion_id))
    institucion = result.scalar_one_or_none()
    if not institucion:
        raise HTTPException(status_code=404, detail="Institución no encontrada")
    return institucion


# --- Facultades ---

@router.get(
    "/facultades",
    response_model=list[FacultadResponse],
    summary="Listar facultades",
)
async def listar_facultades(
    institucion_id: UUID = Query(None, description="Filtrar por institución"),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    query = select(Facultad).order_by(Facultad.nombre)
    if institucion_id:
        query = query.where(Facultad.institucion_id == institucion_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.post(
    "/facultades",
    response_model=FacultadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear facultad",
    description="Solo coordinadores y rectores pueden crear facultades.",
)
async def crear_facultad(
    data: FacultadCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_rol(Rol.ADMIN)),
):
    facultad = Facultad(**data.model_dump())
    db.add(facultad)
    await db.commit()
    await db.refresh(facultad)
    return facultad


# --- Programas ---

@router.get(
    "/programas",
    response_model=list[ProgramaResponse],
    summary="Listar programas",
)
async def listar_programas(
    facultad_id: UUID = Query(None, description="Filtrar por facultad"),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    query = select(Programa).order_by(Programa.nombre)
    if facultad_id:
        query = query.where(Programa.facultad_id == facultad_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.post(
    "/programas",
    response_model=ProgramaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear programa",
    description="Solo coordinadores y rectores pueden crear programas.",
)
async def crear_programa(
    data: ProgramaCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_rol(Rol.ADMIN)),
):
    programa = Programa(**data.model_dump())
    db.add(programa)
    await db.commit()
    await db.refresh(programa)
    return programa


# --- Asignaturas ---

@router.get(
    "/asignaturas",
    response_model=list[AsignaturaResponse],
    summary="Listar asignaturas",
)
async def listar_asignaturas(
    programa_id: UUID = Query(None, description="Filtrar por programa"),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    query = select(Asignatura).order_by(Asignatura.nombre)
    if programa_id:
        query = query.where(Asignatura.programa_id == programa_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.post(
    "/asignaturas",
    response_model=AsignaturaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear asignatura",
    description="Solo coordinadores y rectores pueden crear asignaturas.",
)
async def crear_asignatura(
    data: AsignaturaCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_rol(Rol.ADMIN)),
):
    asignatura = Asignatura(**data.model_dump())
    db.add(asignatura)
    await db.commit()
    await db.refresh(asignatura)
    return asignatura