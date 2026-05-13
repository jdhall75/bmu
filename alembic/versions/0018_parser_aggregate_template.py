"""Add aggregate_template to parser_templates.

Revision ID: 0018_parser_aggregate_tmpl
Revises: 0017_job_show_on_device
Create Date: 2026-05-13
"""

from alembic import op
import sqlalchemy as sa

revision = "0018_parser_aggregate_tmpl"
down_revision = "0017_job_show_on_device"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "parser_templates",
        sa.Column("aggregate_template", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("parser_templates", "aggregate_template")
