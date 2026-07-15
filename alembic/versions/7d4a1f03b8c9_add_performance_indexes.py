"""add_performance_indexes

Revision ID: 7d4a1f03b8c9
Revises: 2c4b6b93e2eb
Create Date: 2026-07-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '7d4a1f03b8c9'
down_revision: Union[str, Sequence[str], None] = '2c4b6b93e2eb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index('ix_solicitudes_estudiante_id', 'solicitudes', ['estudiante_id'])
    op.create_index('ix_solicitudes_estado', 'solicitudes', ['estado'])
    op.create_index('ix_documentos_solicitud_id', 'documentos', ['solicitud_id'])
    op.create_index('ix_historial_estados_solicitud_id', 'historial_estados', ['solicitud_id'])
    op.create_index('ix_homologacion_asignaturas_homologacion_id', 'homologacion_asignaturas', ['homologacion_id'])


def downgrade() -> None:
    op.drop_index('ix_homologacion_asignaturas_homologacion_id', table_name='homologacion_asignaturas')
    op.drop_index('ix_historial_estados_solicitud_id', table_name='historial_estados')
    op.drop_index('ix_documentos_solicitud_id', table_name='documentos')
    op.drop_index('ix_solicitudes_estado', table_name='solicitudes')
    op.drop_index('ix_solicitudes_estudiante_id', table_name='solicitudes')
