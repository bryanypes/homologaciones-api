"""add cedula and telefono to usuarios

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2025-07-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("usuarios", sa.Column("cedula", sa.String(20), nullable=True))
    op.add_column("usuarios", sa.Column("telefono", sa.String(20), nullable=True))
    op.create_unique_constraint("uq_usuarios_cedula", "usuarios", ["cedula"])
    op.create_index("ix_usuarios_cedula", "usuarios", ["cedula"])


def downgrade() -> None:
    op.drop_index("ix_usuarios_cedula", table_name="usuarios")
    op.drop_constraint("uq_usuarios_cedula", "usuarios", type_="unique")
    op.drop_column("usuarios", "telefono")
    op.drop_column("usuarios", "cedula")
