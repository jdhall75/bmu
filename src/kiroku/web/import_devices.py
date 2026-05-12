"""CSV bulk-import / upsert for devices.

Accepts either a file upload or a pasted blob. Headers (case-insensitive,
order doesn't matter):

    name, hostname, port, description, make, model, role, group, platform,
    transport, driver_kind, credentials, enabled

Required: name, hostname, group.
Optional: make, model, role, platform, transport, driver_kind, port,
          description, credentials, enabled.

Upsert behaviour
----------------
* If a device with the given ``name`` does **not** exist it is created.
* If it **does** exist its fields are updated:
    - ``hostname`` is always written (it is required in the CSV).
    - All other fields are only written when the CSV cell is non-blank;
      a blank cell means "leave the existing value unchanged".
    - ``enabled``: blank = leave unchanged (new devices default to True).
    - ``group``: listed groups are **added** to existing group membership;
      no groups are removed.

The whole import runs in a single transaction. If any row fails to
validate, nothing is committed and the results page lists per-row errors.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from kiroku.models import Credential, Device, DeviceGroup, DriverKind, TransportProtocol

REQUIRED = ("name", "hostname", "group")
TRUTHY = {"1", "true", "yes", "y", "t"}
FALSY = {"0", "false", "no", "n", "f"}


@dataclass
class RowResult:
    line: int
    name: str
    ok: bool
    message: str
    action: str = field(default="create")  # "create" | "update"


def _parse_bool(value: str | None) -> bool | None:
    """Return True/False, or None if the cell is blank (= no change)."""
    if value is None or value.strip() == "":
        return None
    v = value.strip().lower()
    if v in TRUTHY:
        return True
    if v in FALSY:
        return False
    raise ValueError(f"invalid boolean: {value!r}")


def _normalize_headers(reader: csv.DictReader) -> dict[str, str]:
    mapping: dict[str, str] = {}
    if reader.fieldnames is None:
        return mapping
    for original in reader.fieldnames:
        key = original.strip().lower()
        if key == "credential":
            key = "credentials"
        mapping[key] = original
    return mapping


def import_csv(db: Session, raw: str) -> tuple[list[RowResult], int, int]:
    """Parse and upsert devices from CSV ``raw``.

    Returns ``(results, created_count, updated_count)``.
    Commits on success; returns without committing if any row has an error.
    """
    reader = csv.DictReader(io.StringIO(raw))
    headers = _normalize_headers(reader)

    results: list[RowResult] = []

    missing = [h for h in REQUIRED if h not in headers]
    if missing:
        results.append(RowResult(
            line=1, name="", ok=False,
            message=f"missing required column(s): {', '.join(missing)}",
        ))
        return results, 0, 0

    # One round-trip per related table.
    groups = {g.name: g for g in db.scalars(select(DeviceGroup)).all()}
    creds = {c.name: c for c in db.scalars(select(Credential)).all()}
    existing: dict[str, Device] = {
        d.name: d
        for d in db.scalars(select(Device).options(selectinload(Device.groups))).all()
    }
    seen_names: set[str] = set()

    pending_add: list[Device] = []
    pending_update: list[Device] = []

    for idx, row in enumerate(reader, start=2):
        get = lambda k: (row.get(headers.get(k, "")) or "").strip()  # noqa: E731
        name = get("name")
        is_update = name in existing
        try:
            if not name:
                raise ValueError("name is required")
            if name in seen_names:
                raise ValueError(f"duplicate name in file: {name!r}")

            hostname = get("hostname")
            if not hostname:
                raise ValueError("hostname is required")

            port_raw = get("port")
            port = int(port_raw) if port_raw else None

            group_names = [n.strip() for n in get("group").split(",") if n.strip()]
            if not group_names:
                raise ValueError("at least one group is required")
            matched_groups: list[DeviceGroup] = []
            for gname in group_names:
                g = groups.get(gname)
                if g is None:
                    raise ValueError(f"unknown group: {gname!r}")
                matched_groups.append(g)

            cred_name = get("credentials")
            credential = None
            if cred_name:
                credential = creds.get(cred_name)
                if credential is None:
                    raise ValueError(f"unknown credential: {cred_name!r}")

            platform_raw = get("platform") or None
            transport_raw = get("transport")
            transport = TransportProtocol(transport_raw) if transport_raw else None
            driver_kind_raw = get("driver_kind")
            driver_kind = DriverKind(driver_kind_raw) if driver_kind_raw else None
            enabled_val = _parse_bool(get("enabled"))

            if is_update:
                device = existing[name]
                device.hostname = hostname
                if port_raw:
                    device.port = port
                if get("description"):
                    device.description = get("description")
                if get("make"):
                    device.make = get("make")
                if get("model"):
                    device.model = get("model")
                if get("role"):
                    device.role = get("role")
                if platform_raw:
                    device.platform = platform_raw
                if transport:
                    device.transport = transport
                if driver_kind:
                    device.driver_kind = driver_kind
                if credential:
                    device.credential_id = credential.id
                if enabled_val is not None:
                    device.enabled = enabled_val
                # Add new groups without removing existing ones.
                existing_group_ids = {g.id for g in device.groups}
                for g in matched_groups:
                    if g.id not in existing_group_ids:
                        device.groups.append(g)
                pending_update.append(device)
                results.append(RowResult(
                    line=idx, name=name, ok=True,
                    message="will be updated", action="update",
                ))
            else:
                device = Device(
                    name=name,
                    hostname=hostname,
                    port=port,
                    description=get("description") or None,
                    make=get("make") or None,
                    model=get("model") or None,
                    role=get("role") or None,
                    platform=platform_raw,
                    transport=transport,
                    driver_kind=driver_kind,
                    credential_id=credential.id if credential else None,
                    enabled=enabled_val if enabled_val is not None else True,
                )
                device.groups = matched_groups
                pending_add.append(device)
                results.append(RowResult(
                    line=idx, name=name, ok=True,
                    message="will be created", action="create",
                ))

            seen_names.add(name)

        except Exception as exc:
            results.append(RowResult(
                line=idx, name=name, ok=False,
                message=str(exc), action="update" if is_update else "create",
            ))

    if any(not r.ok for r in results):
        return results, 0, 0

    for d in pending_add:
        db.add(d)
    db.commit()

    for r in results:
        if r.ok:
            r.message = r.action  # "created" / "updated"

    return results, len(pending_add), len(pending_update)


CSV_TEMPLATE = (
    "name,hostname,port,description,make,model,role,"
    "group,platform,transport,driver_kind,credentials,enabled\r\n"
)
