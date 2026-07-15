"""add_resolucion_to_tipodocumento

Revision ID: 2c4b6b93e2eb
Revises: 1b92889cd72c
Create Date: 2026-07-01 15:36:20.586609

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2c4b6b93e2eb'
down_revision: Union[str, Sequence[str], None] = '1b92889cd72c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE tipodocumento ADD VALUE IF NOT EXISTS 'resolucion'")


def downgrade() -> None:
    pass
