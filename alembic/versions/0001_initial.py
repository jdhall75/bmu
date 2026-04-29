"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-29

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "credentials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "provider",
            sa.Enum("local", "vault", "bitwarden", name="credential_provider"),
            nullable=False,
        ),
        sa.Column("encrypted_payload", sa.LargeBinary(), nullable=True),
        sa.Column("ref", sa.String(512), nullable=True),
        sa.Column("username", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "parser_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "type",
            sa.Enum("textfsm", "ttp", "xslt", name="parser_type"),
            nullable=False,
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("kind", sa.Enum("cli", "netconf", name="profile_kind"), nullable=False),
        sa.Column("platform", sa.String(64), nullable=True),
        sa.Column(
            "transport",
            sa.Enum("ssh", "telnet", "netconf", name="transport_protocol"),
            nullable=True,
        ),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("prompt_pattern", sa.String(256), nullable=True),
        sa.Column("pre_commands", sa.Text(), nullable=True),
        sa.Column("disable_paging_command", sa.String(256), nullable=True),
        sa.Column("commands", sa.Text(), nullable=True),
        sa.Column("manufacturer", sa.String(64), nullable=True),
        sa.Column("rpc", sa.Text(), nullable=True),
        sa.Column(
            "parser_template_id",
            sa.Integer(),
            sa.ForeignKey("parser_templates.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "device_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "default_credential_id",
            sa.Integer(),
            sa.ForeignKey("credentials.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("max_parallel", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "devices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False, unique=True),
        sa.Column("hostname", sa.String(255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "group_id",
            sa.Integer(),
            sa.ForeignKey("device_groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "profile_id",
            sa.Integer(),
            sa.ForeignKey("profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "credential_id",
            sa.Integer(),
            sa.ForeignKey("credentials.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "schedules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "group_id",
            sa.Integer(),
            sa.ForeignKey("device_groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "kind", sa.Enum("backup", "collect", name="job_kind"), nullable=False
        ),
        sa.Column("cron", sa.String(64), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "schedule_id",
            sa.Integer(),
            sa.ForeignKey("schedules.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "device_id",
            sa.Integer(),
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "running",
                "success",
                "failed",
                "timeout",
                "cancelled",
                name="run_status",
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("commit_sha", sa.String(64), nullable=True),
        sa.Column("payload_sha256", sa.String(64), nullable=True),
        sa.Column("bytes_captured", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_runs_device_id_created_at", "runs", ["device_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_runs_device_id_created_at", table_name="runs")
    op.drop_table("runs")
    op.drop_table("schedules")
    op.drop_table("devices")
    op.drop_table("device_groups")
    op.drop_table("profiles")
    op.drop_table("parser_templates")
    op.drop_table("credentials")
    sa.Enum(name="run_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="job_kind").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="profile_kind").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="parser_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="transport_protocol").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="credential_provider").drop(op.get_bind(), checkfirst=True)
