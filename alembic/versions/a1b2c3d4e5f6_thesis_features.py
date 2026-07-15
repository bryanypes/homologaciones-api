"""thesis_features

Revision ID: a1b2c3d4e5f6
Revises: 7d4a1f03b8c9
Create Date: 2026-07-15 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '7d4a1f03b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # estado_ia_original en homologacion_asignaturas
    op.add_column(
        'homologacion_asignaturas',
        sa.Column(
            'estado_ia_original',
            sa.Enum(
                'homologada', 'no_homologada', 'homologada_parcial', 'pendiente',
                name='estadoasignatura',
                create_type=False,
            ),
            nullable=True,
        ),
    )

    # fue_corregida en homologacion_asignaturas
    op.add_column(
        'homologacion_asignaturas',
        sa.Column('fue_corregida', sa.Boolean(), nullable=False, server_default='false'),
    )

    # numero_resolucion en solicitudes
    op.add_column(
        'solicitudes',
        sa.Column('numero_resolucion', sa.String(30), nullable=True),
    )

    # Tabla contador de resoluciones
    op.create_table(
        'resolucion_contador',
        sa.Column('anio', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('ultimo_numero', sa.Integer(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_table('resolucion_contador')
    op.drop_column('solicitudes', 'numero_resolucion')
    op.drop_column('homologacion_asignaturas', 'fue_corregida')
    op.drop_column('homologacion_asignaturas', 'estado_ia_original')
