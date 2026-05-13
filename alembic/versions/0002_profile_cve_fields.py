"""add cve_vendor and cve_product to profiles

Revision ID: 0002_profile_cve_fields
Revises: 0001_initial
Create Date: 2026-05-06

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_profile_cve_fields"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("profiles", sa.Column("cve_vendor", sa.String(64), nullable=True))
    op.add_column("profiles", sa.Column("cve_product", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("profiles", "cve_product")
    op.drop_column("profiles", "cve_vendor")
