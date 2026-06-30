"""add_pendiente_to_estadoasignatura

Revision ID: 9593501dcfad
Revises: 4a0464fddfc9
Create Date: 2026-06-16 19:38:10.887462

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9593501dcfad'
down_revision: Union[str, Sequence[str], None] = '4a0464fddfc9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE estadoasignatura ADD VALUE IF NOT EXISTS 'pendiente'")

def downgrade() -> None:
    pass
