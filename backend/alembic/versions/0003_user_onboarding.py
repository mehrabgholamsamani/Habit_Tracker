"""persist user onboarding state

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TABLE users ADD COLUMN onboarding_completed_at TIMESTAMP"))
    op.execute(sa.text("ALTER TABLE users ADD COLUMN onboarding_version INTEGER NOT NULL DEFAULT 0"))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE users DROP COLUMN IF EXISTS onboarding_version"))
    op.execute(sa.text("ALTER TABLE users DROP COLUMN IF EXISTS onboarding_completed_at"))
