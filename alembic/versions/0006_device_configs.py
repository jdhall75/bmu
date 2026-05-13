"""add device_configs full-text search table and performance indexes

Revision ID: 0006_device_configs
Revises: 0005_run_batches
Create Date: 2026-05-07

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_device_configs"
down_revision: Union[str, None] = "0005_run_batches"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.execute("""
        CREATE TABLE device_configs (
            device_id  INTEGER PRIMARY KEY
                       REFERENCES devices(id) ON DELETE CASCADE,
            batch_id   INTEGER
                       REFERENCES run_batches(id) ON DELETE SET NULL,
            captured_at TIMESTAMPTZ,
            content    TEXT,
            content_fts TSVECTOR
        )
    """)

    op.execute(
        "CREATE INDEX ix_device_configs_fts ON device_configs USING GIN (content_fts)"
    )
    op.execute(
        "CREATE INDEX ix_device_configs_trgm ON device_configs "
        "USING GIN (content gin_trgm_ops)"
    )

    op.create_index("ix_runs_batch_id", "runs", ["batch_id"])


def downgrade() -> None:
    op.drop_index("ix_runs_batch_id", table_name="runs")
    op.execute("DROP TABLE IF EXISTS device_configs")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
