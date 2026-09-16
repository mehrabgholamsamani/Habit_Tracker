"""make check-ins unique per habit and day

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TABLE checkins ADD COLUMN checked_on DATE"))
    op.execute(sa.text("UPDATE checkins SET checked_on = checked_at::date"))
    op.execute(
        sa.text("""
        DELETE FROM checkins duplicate
        USING checkins original
        WHERE duplicate.habit_id = original.habit_id
          AND duplicate.checked_on = original.checked_on
          AND duplicate.id > original.id
        """)
    )
    op.execute(sa.text("ALTER TABLE checkins ALTER COLUMN checked_on SET NOT NULL"))
    op.execute(
        sa.text("""
        ALTER TABLE checkins
        ADD CONSTRAINT uq_checkins_habit_checked_on UNIQUE (habit_id, checked_on)
        """)
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "ALTER TABLE checkins DROP CONSTRAINT IF EXISTS uq_checkins_habit_checked_on"
        )
    )
    op.execute(sa.text("ALTER TABLE checkins DROP COLUMN IF EXISTS checked_on"))
