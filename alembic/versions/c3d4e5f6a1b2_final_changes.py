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
    bind = op.get_bind()
    engine = bind.engine

    # Conexión nueva e independiente de la transacción de Alembic,
    # para que el ALTER TYPE se comprometa de inmediato
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as autocommit_conn:
        autocommit_conn.execute(sa.text("ALTER TYPE rol ADD VALUE IF NOT EXISTS 'vicerrector'"))

    # Esto corre en la transacción normal de la migración, y ya puede
    # usar 'vicerrector' porque fue comprometido por otra conexión
    op.execute("UPDATE usuarios SET rol = 'vicerrector' WHERE rol = 'rector'")

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
    op.execute("UPDATE usuarios SET rol = 'rector' WHERE rol = 'vicerrector'")