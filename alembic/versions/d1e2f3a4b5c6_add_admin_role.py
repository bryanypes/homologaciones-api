"""add admin role

Revision ID: d1e2f3a4b5c6
Revises: c3d4e5f6a1b2
Create Date: 2025-07-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, None] = "c3d4e5f6a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE rol ADD VALUE IF NOT EXISTS 'admin'")


def downgrade() -> None:
    # PostgreSQL no permite eliminar valores de un enum
    pass
