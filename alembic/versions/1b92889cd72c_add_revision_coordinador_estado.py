"""add_revision_coordinador_estado

Revision ID: 1b92889cd72c
Revises: 09a2301938e2
Create Date: 2026-06-29 20:33:19.111417

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1b92889cd72c'
down_revision: Union[str, Sequence[str], None] = '09a2301938e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE estadosolicitud ADD VALUE IF NOT EXISTS 'revision_coordinador'")


def downgrade() -> None:
    pass
