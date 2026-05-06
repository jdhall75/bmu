"""add cve_scan value to job_kind enum

Revision ID: 0003_cve_scan_job_kind
Revises: 0002_profile_cve_fields
Create Date: 2026-05-06

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0003_cve_scan_job_kind"
down_revision: Union[str, None] = "0002_profile_cve_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block.
    op.execute("COMMIT")
    op.execute("ALTER TYPE job_kind ADD VALUE IF NOT EXISTS 'cve_scan'")


def downgrade() -> None:
    # Postgres does not support removing enum values; a full type rebuild is
    # required and is destructive. Leave the value in place on downgrade.
    pass
