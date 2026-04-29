"""CSV bulk-import for devices.

Accepts either a file upload or a pasted blob. Headers (case-insensitive,
order doesn't matter):

    name, hostname, port, description, group, profile, credentials, enabled

Required: name, hostname, group, profile.
``enabled`` accepts 1/0, true/false, yes/no (case-insensitive); blank => true.
``credentials`` is optional; blank means "use the group's default".

The whole import is a single transaction: if any row fails, nothing is
committed. The results page lists per-row outcomes.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from bmu.models import Credential, Device, DeviceGroup, Profile

REQUIRED = ("name", "hostname", "group", "profile")
TRUTHY = {"1", "true", "yes", "y", "t"}
FALSY = {"0", "false", "no", "n", "f"}


@dataclass
class RowResult:
    line: int
    name: str
    ok: bool
    message: str


def _parse_bool(value: str | None) -> bool:
    if value is None or value.strip() == "":
        return True
    v = value.strip().lower()
    if v in TRUTHY:
        return True
    if v in FALSY:
        return False
    raise ValueError(f"invalid boolean: {value!r}")


def _normalize_headers(reader: csv.DictReader) -> dict[str, str]:
    """Map normalized -> original header so we can read either spelling.

    Also accepts ``credential`` as an alias for ``credentials``.
    """
    mapping: dict[str, str] = {}
    if reader.fieldnames is None:
        return mapping
    for original in reader.fieldnames:
        key = original.strip().lower()
        if key == "credential":
            key = "credentials"
        mapping[key] = original
    return mapping


def import_csv(db: Session, raw: str) -> tuple[list[RowResult], int]:
    """Parse and load devices from CSV ``raw``. Returns (results, created_count).

    Commits on success, rolls back if any row failed.
    """
    reader = csv.DictReader(io.StringIO(raw))
    headers = _normalize_headers(reader)

    results: list[RowResult] = []
    pending: list[Device] = []

    missing = [h for h in REQUIRED if h not in headers]
    if missing:
        results.append(
            RowResult(
                line=1, name="",
                ok=False,
                message=f"missing required column(s): {', '.join(missing)}",
            )
        )
        return results, 0

    # Cache name -> id lookups; one round-trip per related table.
    groups = {g.name: g for g in db.scalars(select(DeviceGroup)).all()}
    profiles = {p.name: p for p in db.scalars(select(Profile)).all()}
    creds = {c.name: c for c in db.scalars(select(Credential)).all()}
    existing_devices = {d.name for d in db.scalars(select(Device.name)).all()}
    seen_names: set[str] = set()

    for idx, row in enumerate(reader, start=2):  # account for header line
        get = lambda k: (row.get(headers.get(k, "")) or "").strip()
        name = get("name")
        try:
            if not name:
                raise ValueError("name is required")
            if name in seen_names:
                raise ValueError(f"duplicate name in file: {name!r}")
            if name in existing_devices:
                raise ValueError(f"device already exists: {name!r}")

            hostname = get("hostname")
            if not hostname:
                raise ValueError("hostname is required")

            port_raw = get("port")
            port = int(port_raw) if port_raw else None

            group_name = get("group")
            group = groups.get(group_name)
            if group is None:
                raise ValueError(f"unknown group: {group_name!r}")

            profile_name = get("profile")
            profile = profiles.get(profile_name)
            if profile is None:
                raise ValueError(f"unknown profile: {profile_name!r}")

            cred_name = get("credentials")
            credential = None
            if cred_name:
                credential = creds.get(cred_name)
                if credential is None:
                    raise ValueError(f"unknown credential: {cred_name!r}")

            enabled = _parse_bool(get("enabled"))

            device = Device(
                name=name,
                hostname=hostname,
                port=port,
                description=get("description") or None,
                group_id=group.id,
                profile_id=profile.id,
                credential_id=credential.id if credential else None,
                enabled=enabled,
            )
            pending.append(device)
            seen_names.add(name)
            results.append(RowResult(line=idx, name=name, ok=True, message="will be created"))
        except Exception as exc:
            results.append(RowResult(line=idx, name=name, ok=False, message=str(exc)))

    if any(not r.ok for r in results):
        return results, 0

    for d in pending:
        db.add(d)
    db.commit()
    for r in results:
        if r.ok:
            r.message = "created"
    return results, len(pending)
