from __future__ import annotations

from litestar import Router, get, post
from litestar.enums import RequestEncodingType
from litestar.exceptions import NotFoundException
from litestar.params import Body
from litestar.response import Redirect, Template
from litestar.status_codes import HTTP_303_SEE_OTHER
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from kiroku.compliance import (
    OPERATORS,
    PARSER_TYPES,
    SEVERITIES,
    run_policy_for_devices,
    scoped_device_ids,
    upsert_compliance_results,
)
from kiroku.models import Device, DeviceGroup
from kiroku.models.compliance import ComplianceCheck, CompliancePolicy
from kiroku.web.deps import provide_db
from kiroku.web.helpers import parse_ids

_MODES = ("any", "all", "none")
_SEVERITY_ORDER = {"critical": 0, "major": 1, "minor": 2, "info": 3}


def _form_context(db: Session, policy=None) -> dict:
    return {
        "policy": policy,
        "parser_types": PARSER_TYPES,
        "operators": OPERATORS,
        "modes": _MODES,
        "severities": SEVERITIES,
        "device_groups": db.scalars(select(DeviceGroup).order_by(DeviceGroup.name)).all(),
        "devices": db.scalars(select(Device).order_by(Device.name)).all(),
    }


def _apply_policy_data(policy: CompliancePolicy, data: dict, db: Session) -> None:
    policy.name = data["name"]
    policy.description = data.get("description") or None
    policy.parser_type = data["parser_type"]
    policy.parser_body = data["parser_body"]
    policy.enabled = data.get("enabled") == "1"
    policy.auto_evaluate = data.get("auto_evaluate") == "1"

    group_ids = parse_ids(data, "device_group_ids")
    device_ids = parse_ids(data, "device_ids")
    policy.device_groups = (
        db.scalars(select(DeviceGroup).where(DeviceGroup.id.in_(group_ids))).all()
        if group_ids else []
    )
    policy.devices = (
        db.scalars(select(Device).where(Device.id.in_(device_ids))).all()
        if device_ids else []
    )

    # Rebuild checks from parallel form arrays.
    names = data.get("check_name", [])
    if isinstance(names, str):
        names = [names]
    fields     = _as_list(data.get("check_field", []))
    operators  = _as_list(data.get("check_operator", []))
    expecteds  = _as_list(data.get("check_expected", []))
    modes      = _as_list(data.get("check_mode", []))
    severities = _as_list(data.get("check_severity", []))
    descs      = _as_list(data.get("check_description", []))
    ids        = _as_list(data.get("check_id", []))

    existing = {c.id: c for c in policy.checks}
    kept_ids: set[int] = set()

    for i, name in enumerate(names):
        name = name.strip()
        if not name:
            continue
        check_id_str = ids[i] if i < len(ids) else ""
        check_id = int(check_id_str) if check_id_str.strip().isdigit() else None

        if check_id and check_id in existing:
            check = existing[check_id]
            kept_ids.add(check_id)
        else:
            check = ComplianceCheck(policy_id=policy.id or 0)
            policy.checks.append(check)

        check.name        = name
        check.field       = fields[i].strip()     if i < len(fields)     else ""
        check.operator    = operators[i]           if i < len(operators)  else "eq"
        check.expected    = expecteds[i] or None   if i < len(expecteds)  else None
        check.mode        = modes[i]               if i < len(modes)      else "any"
        check.severity    = severities[i]          if i < len(severities) else "major"
        check.description = descs[i] or None       if i < len(descs)      else None
        check.sort_order  = i

    # Remove checks that were deleted in the form.
    for cid, check in list(existing.items()):
        if cid not in kept_ids:
            policy.checks.remove(check)
            db.delete(check)


def _as_list(val) -> list[str]:
    if isinstance(val, str):
        return [val]
    return list(val) if val else []


def _scoped_devices(policy: CompliancePolicy, db: Session) -> list[Device]:
    """Expand group + direct device scope, deduplicated and sorted by name."""
    ids = scoped_device_ids(policy)
    id_set = set(ids)
    all_devs: dict[int, Device] = {}
    for g in policy.device_groups:
        for d in g.devices:
            if d.id in id_set:
                all_devs[d.id] = d
    for d in policy.devices:
        if d.id in id_set:
            all_devs[d.id] = d
    return sorted(all_devs.values(), key=lambda d: d.name)


def _run_policy(policy: CompliancePolicy, db: Session) -> None:
    """Evaluate policy against all scoped devices and upsert results."""
    device_ids = scoped_device_ids(policy)
    if not device_ids:
        return
    rows = db.execute(
        text("SELECT device_id, content FROM device_configs WHERE device_id = ANY(:ids)"),
        {"ids": device_ids},
    ).mappings().all()
    content_map = {r["device_id"]: r["content"] for r in rows}
    pairs = [(did, content_map.get(did)) for did in device_ids]
    results = run_policy_for_devices(policy, pairs)
    upsert_compliance_results(db, results)


def _last_results(policy: CompliancePolicy) -> dict:
    """Summarise last results: {total, pass, fail, error, skip}."""
    counts = {"pass": 0, "fail": 0, "error": 0, "skip": 0}
    for r in policy.results:
        counts[r.status] = counts.get(r.status, 0) + 1
    counts["total"] = sum(counts.values())
    return counts


@get("/", dependencies={"db": provide_db})
async def list_policies(db: Session) -> Template:
    policies = db.scalars(select(CompliancePolicy).order_by(CompliancePolicy.name)).all()
    summaries = {p.id: _last_results(p) for p in policies}
    return Template(
        template_name="compliance/list.html",
        context={"policies": policies, "summaries": summaries},
    )


@get("/new", dependencies={"db": provide_db})
async def new_policy_form(db: Session) -> Template:
    return Template(template_name="compliance/form.html", context=_form_context(db))


@post("/", dependencies={"db": provide_db})
async def create_policy(
    db: Session,
    data: dict = Body(media_type=RequestEncodingType.URL_ENCODED),
) -> Redirect:
    policy = CompliancePolicy(
        name=data["name"],
        parser_type=data["parser_type"],
        parser_body=data["parser_body"],
    )
    db.add(policy)
    db.flush()
    _apply_policy_data(policy, data, db)
    db.commit()
    return Redirect(f"/compliance/{policy.id}", status_code=HTTP_303_SEE_OTHER)


@get("/{policy_id:int}", dependencies={"db": provide_db})
async def view_policy(policy_id: int, db: Session) -> Template:
    policy = db.get(CompliancePolicy, policy_id)
    if policy is None:
        raise NotFoundException(detail=f"Policy {policy_id} not found")
    devices = _scoped_devices(policy, db)
    result_map = {r.device_id: r for r in policy.results}
    return Template(
        template_name="compliance/detail.html",
        context={
            "policy": policy,
            "devices": devices,
            "result_map": result_map,
            "summary": _last_results(policy),
        },
    )


@get("/{policy_id:int}/edit", dependencies={"db": provide_db})
async def edit_policy_form(policy_id: int, db: Session) -> Template:
    policy = db.get(CompliancePolicy, policy_id)
    if policy is None:
        raise NotFoundException(detail=f"Policy {policy_id} not found")
    ctx = _form_context(db, policy)
    return Template(template_name="compliance/form.html", context=ctx)


@post("/{policy_id:int}", dependencies={"db": provide_db})
async def update_policy(
    policy_id: int,
    db: Session,
    data: dict = Body(media_type=RequestEncodingType.URL_ENCODED),
) -> Redirect:
    policy = db.get(CompliancePolicy, policy_id)
    if policy is None:
        raise NotFoundException(detail=f"Policy {policy_id} not found")
    _apply_policy_data(policy, data, db)
    db.commit()
    return Redirect(f"/compliance/{policy_id}", status_code=HTTP_303_SEE_OTHER)


@post("/{policy_id:int}/run", dependencies={"db": provide_db})
async def run_policy(policy_id: int, db: Session) -> Redirect:
    policy = db.get(CompliancePolicy, policy_id)
    if policy is None:
        raise NotFoundException(detail=f"Policy {policy_id} not found")
    _run_policy(policy, db)
    db.commit()
    return Redirect(f"/compliance/{policy_id}", status_code=HTTP_303_SEE_OTHER)


@post("/{policy_id:int}/delete", dependencies={"db": provide_db})
async def delete_policy(policy_id: int, db: Session) -> Redirect:
    policy = db.get(CompliancePolicy, policy_id)
    if policy is None:
        raise NotFoundException(detail=f"Policy {policy_id} not found")
    db.delete(policy)
    db.commit()
    return Redirect("/compliance", status_code=HTTP_303_SEE_OTHER)


router = Router(
    path="/compliance",
    route_handlers=[
        list_policies,
        new_policy_form,
        create_policy,
        view_policy,
        edit_policy_form,
        update_policy,
        run_policy,
        delete_policy,
    ],
)
