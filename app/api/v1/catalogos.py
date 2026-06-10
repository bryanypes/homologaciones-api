from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.catalogo import Pais, Departamento, Municipio
from app.schemas.catalogo import PaisResponse, DepartamentoResponse, MunicipioResponse

router = APIRouter(prefix="/catalogos", tags=["Catálogos geográficos"])


@router.get(
    "/paises",
    response_model=list[PaisResponse],
    summary="Listar países",
    description="Retorna todos los países disponibles.",
)
async def listar_paises(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    result = await db.execute(select(Pais).order_by(Pais.nombre))
    return result.scalars().all()


@router.get(
    "/departamentos",
    response_model=list[DepartamentoResponse],
    summary="Listar departamentos",
    description="Retorna departamentos. Filtrar por pais_id para obtener solo los de un país.",
)
async def listar_departamentos(
    pais_id: UUID = Query(None, description="Filtrar por país"),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    query = select(Departamento).order_by(Departamento.nombre)
    if pais_id:
        query = query.where(Departamento.pais_id == pais_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.get(
    "/municipios",
    response_model=list[MunicipioResponse],
    summary="Listar municipios",
    description="Retorna municipios. Filtrar por departamento_id para obtener solo los de un departamento.",
)
async def listar_municipios(
    departamento_id: UUID = Query(None, description="Filtrar por departamento"),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    query = select(Municipio).order_by(Municipio.nombre)
    if departamento_id:
        query = query.where(Municipio.departamento_id == departamento_id)
    result = await db.execute(query)
    return result.scalars().all()