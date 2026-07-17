"""final changes: vicerrector role + asignatura fields

Revision ID: c3d4e5f6a1b2
Revises: a1b2c3d4e5f6
Create Date: 2025-07-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a1b2'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()

    # 1. Agregar 'vicerrector' al enum de rol, fuera de la transacción
    #    principal para que quede comprometido antes de usarlo
    with connection.execution_options(isolation_level="AUTOCOMMIT"):
        connection.execute(sa.text("ALTER TYPE rol ADD VALUE IF NOT EXISTS 'vicerrector'"))

    # 2. Migrar usuarios existentes con rol 'rector' a 'vicerrector'
    op.execute("UPDATE usuarios SET rol = 'vicerrector' WHERE rol = 'rector'")

    # 3. Agregar campos al modelo Asignatura para pensum completo
    op.add_column('asignaturas', sa.Column('codigo', sa.String(50), nullable=True))
    op.add_column('asignaturas', sa.Column('semestre', sa.Integer(), nullable=True))
    op.add_column('asignaturas', sa.Column('tipo', sa.String(10), nullable=True))
    op.add_column('asignaturas', sa.Column('intensidad_horaria', sa.Integer(), nullable=True))
    op.add_column('asignaturas', sa.Column('linea_continuidad', sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column('asignaturas', 'linea_continuidad')
    op.drop_column('asignaturas', 'intensidad_horaria')
    op.drop_column('asignaturas', 'tipo')
    op.drop_column('asignaturas', 'semestre')
    op.drop_column('asignaturas', 'codigo')
    # Revertir usuarios (nota: el valor 'vicerrector' queda en el enum pero sin usuarios)
    op.execute("UPDATE usuarios SET rol = 'rector' WHERE rol = 'vicerrector'")