"""Add is_default flag to credentials table.

Revision ID: 0013_credential_default
Revises: 0012_run_parsed_data
Create Date: 2026-05-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0013_credential_default"
down_revision = "0012_run_parsed_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "credentials",
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
    )
    # At most one row may have is_default = true.
    op.create_index(
        "uix_credentials_is_default",
        "credentials",
        ["is_default"],
        unique=True,
        postgresql_where=sa.text("is_default = true"),
    )


def downgrade() -> None:
    op.drop_index("uix_credentials_is_default", table_name="credentials")
    op.drop_column("credentials", "is_default")
