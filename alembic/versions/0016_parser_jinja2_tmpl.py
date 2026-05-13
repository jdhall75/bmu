"""Add jinja2_template to parser_templates; add parser_template_id FK to runs.

Revision ID: 0016_parser_jinja2_tmpl
Revises: 0015_run_parse_error
Create Date: 2026-05-12
"""

from alembic import op
import sqlalchemy as sa

revision = "0016_parser_jinja2_tmpl"
down_revision = "0015_run_parse_error"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "parser_templates", sa.Column("jinja2_template", sa.Text(), nullable=True)
    )
    op.add_column(
        "runs",
        sa.Column(
            "parser_template_id",
            sa.Integer(),
            sa.ForeignKey("parser_templates.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("runs", "parser_template_id")
    op.drop_column("parser_templates", "jinja2_template")
