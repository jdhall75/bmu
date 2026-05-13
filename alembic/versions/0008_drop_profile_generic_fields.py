"""drop prompt_pattern, pre_commands, disable_paging_command from profiles

These fields were used by the old generic/unknown-platform path. Platform
behaviour (prompt patterns, mode transitions, paging) is now handled
entirely by the operator-defined Platform YAML via custom_platform_id.

Revision ID: 0008_drop_profile_generic_fields
Revises: 0007_custom_platforms
Create Date: 2026-05-07

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_drop_profile_generic_fields"
down_revision: Union[str, None] = "0007_custom_platforms"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("profiles", "prompt_pattern")
    op.drop_column("profiles", "pre_commands")
    op.drop_column("profiles", "disable_paging_command")


def downgrade() -> None:
    op.add_column(
        "profiles", sa.Column("disable_paging_command", sa.String(256), nullable=True)
    )
    op.add_column("profiles", sa.Column("pre_commands", sa.Text(), nullable=True))
    op.add_column(
        "profiles", sa.Column("prompt_pattern", sa.String(256), nullable=True)
    )
