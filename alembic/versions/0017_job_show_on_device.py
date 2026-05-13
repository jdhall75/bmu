"""Add show_on_device to jobs; add job_id FK to runs.

Revision ID: 0017_job_show_on_device
Revises: 0016_parser_jinja2_tmpl
Create Date: 2026-05-12
"""

from alembic import op
import sqlalchemy as sa

revision = "0017_job_show_on_device"
down_revision = "0016_parser_jinja2_tmpl"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "show_on_device", sa.Boolean(), nullable=False, server_default="false"
        ),
    )
    op.add_column(
        "runs",
        sa.Column(
            "job_id",
            sa.Integer(),
            sa.ForeignKey("jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("runs", "job_id")
    op.drop_column("jobs", "show_on_device")
