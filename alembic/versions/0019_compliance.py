"""Add compliance policies, checks, and results tables

Revision ID: 0019_compliance
Revises: 0018_parser_aggregate_tmpl
Create Date: 2026-05-13

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0019_compliance"
down_revision: Union[str, None] = "0018_parser_aggregate_tmpl"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "compliance_policies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("parser_type", sa.String(16), nullable=False),
        sa.Column("parser_body", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("auto_evaluate", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "compliance_policy_groups",
        sa.Column("policy_id", sa.Integer(), sa.ForeignKey("compliance_policies.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("device_group_id", sa.Integer(), sa.ForeignKey("device_groups.id", ondelete="CASCADE"), primary_key=True),
    )

    op.create_table(
        "compliance_policy_devices",
        sa.Column("policy_id", sa.Integer(), sa.ForeignKey("compliance_policies.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True),
    )

    op.create_table(
        "compliance_checks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("policy_id", sa.Integer(), sa.ForeignKey("compliance_policies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("field", sa.String(64), nullable=False),
        sa.Column("operator", sa.String(16), nullable=False),
        sa.Column("expected", sa.Text(), nullable=True),
        sa.Column("mode", sa.String(8), nullable=False, server_default="any"),
        sa.Column("severity", sa.String(8), nullable=False, server_default="major"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_compliance_checks_policy_id", "compliance_checks", ["policy_id"])

    op.create_table(
        "compliance_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("policy_id", sa.Integer(), sa.ForeignKey("compliance_policies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(8), nullable=False),
        sa.Column("detail", JSONB(), nullable=True),
        sa.UniqueConstraint("policy_id", "device_id", name="uq_compliance_results_policy_device"),
    )
    op.create_index("ix_compliance_results_policy_id", "compliance_results", ["policy_id"])
    op.create_index("ix_compliance_results_device_id", "compliance_results", ["device_id"])


def downgrade() -> None:
    op.drop_table("compliance_results")
    op.drop_table("compliance_checks")
    op.drop_table("compliance_policy_devices")
    op.drop_table("compliance_policy_groups")
    op.drop_table("compliance_policies")
