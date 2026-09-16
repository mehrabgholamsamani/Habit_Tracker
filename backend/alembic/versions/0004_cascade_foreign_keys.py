"""make ownership deletes database-enforced

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
    op.execute(sa.text("ALTER TABLE checkins DROP CONSTRAINT checkins_habit_id_fkey"))
    op.execute(sa.text("""
        ALTER TABLE checkins ADD CONSTRAINT checkins_habit_id_fkey
        FOREIGN KEY (habit_id) REFERENCES habits(id) ON DELETE CASCADE
    """))
    op.execute(sa.text("ALTER TABLE habits DROP CONSTRAINT habits_user_id_fkey"))
    op.execute(sa.text("""
        ALTER TABLE habits ADD CONSTRAINT habits_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    """))


def downgrade() -> None:
    op.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
    op.execute(sa.text("ALTER TABLE habits DROP CONSTRAINT habits_user_id_fkey"))
    op.execute(sa.text("""
        ALTER TABLE habits ADD CONSTRAINT habits_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES users(id)
    """))
    op.execute(sa.text("ALTER TABLE checkins DROP CONSTRAINT checkins_habit_id_fkey"))
    op.execute(sa.text("""
        ALTER TABLE checkins ADD CONSTRAINT checkins_habit_id_fkey
        FOREIGN KEY (habit_id) REFERENCES habits(id)
    """))
