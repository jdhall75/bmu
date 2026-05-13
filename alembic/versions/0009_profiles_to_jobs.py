"""profiles_to_jobs: merge Profile into Job, add device driver config columns

Revision ID: 0009_profiles_to_jobs
Revises: 0008_drop_profile_generic_fields
Create Date: 2026-05-07

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_profiles_to_jobs"
down_revision: Union[str, None] = "0008_drop_profile_generic_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Add device driver-config columns (populated from profile below)
    # ------------------------------------------------------------------
    op.add_column("devices", sa.Column("platform", sa.String(64), nullable=True))
    op.add_column(
        "devices",
        sa.Column(
            "transport",
            sa.Enum(name="transport_protocol", create_type=False),
            nullable=True,
        ),
    )
    op.add_column("devices", sa.Column("driver_kind", sa.String(8), nullable=True))
    op.add_column(
        "devices",
        sa.Column(
            "custom_platform_id",
            sa.Integer,
            sa.ForeignKey("platforms.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # Populate device driver config from the associated profile.
    op.execute("""
        UPDATE devices d
        SET
            platform           = p.platform,
            transport          = p.transport,
            driver_kind        = p.kind,
            custom_platform_id = p.custom_platform_id
        FROM profiles p
        WHERE d.profile_id = p.id
    """)

    # ------------------------------------------------------------------
    # 2. Rename profiles -> jobs
    # ------------------------------------------------------------------
    op.rename_table("profiles", "jobs")

    # ------------------------------------------------------------------
    # 3. Rename the old profile kind column to a temp name
    # ------------------------------------------------------------------
    op.alter_column("jobs", "kind", new_column_name="profile_kind_tmp")

    # ------------------------------------------------------------------
    # 4. Add jobs.kind (backup/collect/cve_scan) reusing existing enum
    # ------------------------------------------------------------------
    op.add_column(
        "jobs",
        sa.Column(
            "kind",
            sa.Enum(name="job_kind", create_type=False),
            nullable=True,
        ),
    )

    # Populate: use the schedule kind for the profile if we can link
    # profiles -> devices -> schedules (via device group).
    # Fall back to 'backup' for any that can't be resolved.
    op.execute("""
        UPDATE jobs j
        SET kind = sq.job_kind
        FROM (
            SELECT
                d.profile_id,
                mode() WITHIN GROUP (ORDER BY s.kind) AS job_kind
            FROM devices d
            JOIN schedules s ON s.group_id = d.group_id
            WHERE d.profile_id IS NOT NULL
            GROUP BY d.profile_id
        ) sq
        WHERE j.id = sq.profile_id
    """)

    # Default remaining rows to 'backup'
    op.execute("UPDATE jobs SET kind = 'backup' WHERE kind IS NULL")

    # Make NOT NULL now that all rows are populated
    op.alter_column("jobs", "kind", nullable=False)

    # ------------------------------------------------------------------
    # 5. Create join tables
    # ------------------------------------------------------------------
    op.create_table(
        "job_device_groups",
        sa.Column(
            "job_id",
            sa.Integer,
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "device_group_id",
            sa.Integer,
            sa.ForeignKey("device_groups.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "job_devices",
        sa.Column(
            "job_id",
            sa.Integer,
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "device_id",
            sa.Integer,
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    # ------------------------------------------------------------------
    # 6. Populate job_device_groups from existing device->profile mapping
    # ------------------------------------------------------------------
    op.execute("""
        INSERT INTO job_device_groups (job_id, device_group_id)
        SELECT DISTINCT profile_id, group_id
        FROM devices
        WHERE profile_id IS NOT NULL
        ON CONFLICT DO NOTHING
    """)

    # ------------------------------------------------------------------
    # 7. Add schedules.job_id; migrate from group_id; drop old columns
    # ------------------------------------------------------------------
    op.add_column(
        "schedules",
        sa.Column(
            "job_id",
            sa.Integer,
            sa.ForeignKey("jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # For each schedule, pick the most common profile_id among enabled
    # devices in the schedule's group.
    op.execute("""
        UPDATE schedules s
        SET job_id = sq.profile_id
        FROM (
            SELECT
                sched.id AS schedule_id,
                mode() WITHIN GROUP (ORDER BY d.profile_id) AS profile_id
            FROM schedules sched
            JOIN devices d ON d.group_id = sched.group_id AND d.enabled = true
            WHERE d.profile_id IS NOT NULL
            GROUP BY sched.id
        ) sq
        WHERE s.id = sq.schedule_id
    """)

    # Drop FK + columns from schedules
    op.drop_constraint("schedules_group_id_fkey", "schedules", type_="foreignkey")
    op.drop_column("schedules", "group_id")
    op.drop_column("schedules", "kind")

    # ------------------------------------------------------------------
    # 8. Drop now-redundant columns from jobs
    # ------------------------------------------------------------------
    op.drop_constraint("profiles_custom_platform_id_fkey", "jobs", type_="foreignkey")
    op.drop_column("jobs", "profile_kind_tmp")
    op.drop_column("jobs", "platform")
    op.drop_column("jobs", "transport")
    op.drop_column("jobs", "port")
    op.drop_column("jobs", "custom_platform_id")
    op.drop_column("jobs", "manufacturer")

    # ------------------------------------------------------------------
    # 9. Drop profile_id from devices
    # ------------------------------------------------------------------
    op.drop_constraint("devices_profile_id_fkey", "devices", type_="foreignkey")
    op.drop_column("devices", "profile_id")

    # ------------------------------------------------------------------
    # 10. Drop the old profile_kind enum
    # ------------------------------------------------------------------
    sa.Enum(name="profile_kind").drop(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    pass
