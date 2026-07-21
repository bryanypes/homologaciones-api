"""initial

Revision ID: c4c36348f794
Revises: 
Create Date: 2026-06-08 20:31:03.043414

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'c4c36348f794'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table('usuarios',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('nombre', sa.String(length=100), nullable=False),
    sa.Column('apellido', sa.String(length=100), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('rol', sa.Enum('estudiante', 'coordinador', 'rector', name='rol'), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('creado_en', sa.DateTime(), nullable=False),
    sa.Column('actualizado_en', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_usuarios_email'), 'usuarios', ['email'], unique=True)

    op.create_table('solicitudes',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('estudiante_id', sa.UUID(), nullable=False),
    sa.Column('institucion_origen', sa.String(length=255), nullable=False),
    sa.Column('programa_origen', sa.String(length=255), nullable=False),
    sa.Column('institucion_destino', sa.String(length=255), nullable=False),
    sa.Column('programa_destino', sa.String(length=255), nullable=False),
    sa.Column('estado', sa.Enum('borrador', 'enviada', 'en_revision', 'procesando_ia', 'pendiente_rector', 'aprobada', 'rechazada', name='estadosolicitud'), nullable=False),
    sa.Column('observaciones', sa.Text(), nullable=True),
    sa.Column('creado_en', sa.DateTime(), nullable=False),
    sa.Column('actualizado_en', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['estudiante_id'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('id')
    )

    op.create_table('documentos',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('solicitud_id', sa.UUID(), nullable=False),
    sa.Column('tipo', sa.Enum('pensum_origen', 'pensum_destino', 'homologacion_generada', name='tipodocumento'), nullable=False),
    sa.Column('nombre_original', sa.String(length=255), nullable=False),
    sa.Column('ruta', sa.String(length=500), nullable=False),
    sa.Column('mime_type', sa.String(length=100), nullable=False),
    sa.Column('tamano_bytes', sa.Integer(), nullable=False),
    sa.Column('creado_en', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['solicitud_id'], ['solicitudes.id'], ),
    sa.PrimaryKeyConstraint('id')
    )

    op.create_table('historial_estados',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('solicitud_id', sa.UUID(), nullable=False),
    sa.Column('usuario_id', sa.UUID(), nullable=False),
    sa.Column('estado_anterior', sa.Enum('borrador', 'enviada', 'en_revision', 'procesando_ia', 'pendiente_rector', 'aprobada', 'rechazada', name='estadosolicitud', create_type=False), nullable=True),
    sa.Column('estado_nuevo', sa.Enum('borrador', 'enviada', 'en_revision', 'procesando_ia', 'pendiente_rector', 'aprobada', 'rechazada', name='estadosolicitud', create_type=False), nullable=False),
    sa.Column('observacion', sa.Text(), nullable=True),
    sa.Column('creado_en', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['solicitud_id'], ['solicitudes.id'], ),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('id')
    )

    op.create_table('homologaciones',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('solicitud_id', sa.UUID(), nullable=False),
    sa.Column('documento_generado_id', sa.UUID(), nullable=True),
    sa.Column('resumen_ia', sa.Text(), nullable=True),
    sa.Column('tokens_utilizados', sa.Integer(), nullable=True),
    sa.Column('creado_en', sa.DateTime(), nullable=False),
    sa.Column('actualizado_en', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['documento_generado_id'], ['documentos.id'], ),
    sa.ForeignKeyConstraint(['solicitud_id'], ['solicitudes.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('solicitud_id')
    )

    op.create_table('homologacion_asignaturas',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('homologacion_id', sa.UUID(), nullable=False),
    sa.Column('asignatura_origen', sa.String(length=255), nullable=False),
    sa.Column('creditos_origen', sa.Float(), nullable=True),
    sa.Column('asignatura_destino', sa.String(length=255), nullable=True),
    sa.Column('creditos_destino', sa.Float(), nullable=True),
    sa.Column('estado', sa.Enum('homologada', 'no_homologada', 'homologada_parcial', name='estadoasignatura'), nullable=False),
    sa.Column('justificacion', sa.Text(), nullable=True),
    sa.Column('similitud_porcentaje', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['homologacion_id'], ['homologaciones.id'], ),
    sa.PrimaryKeyConstraint('id')
    )

def downgrade() -> None:
    op.drop_table('homologacion_asignaturas')
    op.drop_table('homologaciones')
    op.drop_table('historial_estados')
    op.drop_table('documentos')
    op.drop_table('solicitudes')
    op.drop_index(op.f('ix_usuarios_email'), table_name='usuarios')
    op.drop_table('usuarios')

    op.execute("DROP TYPE IF EXISTS estadoasignatura CASCADE;")
    op.execute("DROP TYPE IF EXISTS tipodocumento CASCADE;")
    op.execute("DROP TYPE IF EXISTS estadosolicitud CASCADE;")
    op.execute("DROP TYPE IF EXISTS rol CASCADE;")