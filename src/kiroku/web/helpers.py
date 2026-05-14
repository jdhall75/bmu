"""Shared utilities for web route handlers."""

from __future__ import annotations

from jinja2.sandbox import SandboxedEnvironment
from sqlalchemy import select, union
from sqlalchemy.orm import Session

from kiroku.models import Device, DeviceGroup

# Shared sandboxed Jinja2 environment for rendering user-supplied templates
# in run detail and job data views.
sandbox = SandboxedEnvironment(autoescape=False)


def parse_ids(data: dict, key: str = "ids") -> list[int]:
    """Extract a list of integer IDs from form data.

    Handles both a single string value and a list (multi-select).
    """
    raw = data.get(key, [])
    if isinstance(raw, str):
        raw = [raw]
    return [int(i) for i in raw if i]


def worker_pools(db: Session) -> list[str]:
    """Return sorted distinct worker_pool names from devices and groups."""
    device_pools = select(Device.worker_pool).where(Device.worker_pool.is_not(None))
    group_pools = select(DeviceGroup.worker_pool).where(DeviceGroup.worker_pool.is_not(None))
    rows = db.execute(union(device_pools, group_pools)).scalars().all()
    return sorted(set(rows))
