"""fix_add_pendiente_enum

Revision ID: 13e0027db1e9
Revises: c6d0741549a5
Create Date: 2026-06-16 19:51:21.034337

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '13e0027db1e9'
down_revision: Union[str, Sequence[str], None] = 'c6d0741549a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE estadoasignatura ADD VALUE IF NOT EXISTS 'pendiente'")

def downgrade() -> None:
    pass
