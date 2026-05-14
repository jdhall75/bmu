"""Compliance evaluation engine.

Parses stored device config text against a CompliancePolicy and evaluates
each ComplianceCheck. All evaluation is offline — no device connections.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from kiroku import parsers as _parsers
from kiroku.logging import get_logger

if TYPE_CHECKING:
    from kiroku.models.compliance import ComplianceCheck, CompliancePolicy

log = get_logger(__name__)

OPERATORS = ("eq", "ne", "contains", "not_contains", "regex", "gt", "lt", "ge", "le", "exists", "not_exists")
MODES = ("any", "all", "none")
SEVERITIES = ("critical", "major", "minor", "info")
PARSER_TYPES = ("textfsm", "ttp", "parse")


def _coerce(a: str, b: str) -> tuple:
    """Try to return (float, float); fall back to (str, str)."""
    try:
        return float(a), float(b)
    except (ValueError, TypeError):
        return str(a), str(b)


def _satisfies(row: dict, check: ComplianceCheck) -> bool:
    """Return True if this single row satisfies the check's condition."""
    op = check.operator
    field = check.field
    expected = check.expected or ""

    if op == "exists":
        return bool(row.get(field))
    if op == "not_exists":
        return not row.get(field)

    value = row.get(field, "")

    if op == "eq":
        a, b = _coerce(str(value), expected)
        return a == b
    if op == "ne":
        a, b = _coerce(str(value), expected)
        return a != b
    if op == "contains":
        return expected.lower() in str(value).lower()
    if op == "not_contains":
        return expected.lower() not in str(value).lower()
    if op == "regex":
        return bool(re.search(expected, str(value), re.IGNORECASE))
    if op in ("gt", "lt", "ge", "le"):
        try:
            a, b = float(value), float(expected)
        except (ValueError, TypeError):
            return False
        return {"gt": a > b, "lt": a < b, "ge": a >= b, "le": a <= b}[op]
    return False


def _evaluate_check(check: ComplianceCheck, rows: list[dict]) -> dict:
    """Evaluate one check against all parsed rows. Returns a check-outcome dict."""
    if not rows:
        # No rows parsed — treat as failing for any/all, passing for none.
        passed = check.mode == "none"
        return {
            "check_id": check.id,
            "name": check.name,
            "field": check.field,
            "operator": check.operator,
            "expected": check.expected,
            "mode": check.mode,
            "severity": check.severity,
            "description": check.description,
            "status": "pass" if passed else "fail",
            "failing_rows": [],
        }

    satisfying = [r for r in rows if _satisfies(r, check)]
    failing = [r for r in rows if not _satisfies(r, check)]

    if check.mode == "any":
        passed = len(satisfying) > 0
    elif check.mode == "all":
        passed = len(failing) == 0
    else:  # none
        passed = len(satisfying) == 0

    return {
        "check_id": check.id,
        "name": check.name,
        "field": check.field,
        "operator": check.operator,
        "expected": check.expected,
        "mode": check.mode,
        "severity": check.severity,
        "description": check.description,
        "status": "pass" if passed else "fail",
        "failing_rows": failing if not passed else [],
    }


def evaluate_policy(policy: CompliancePolicy, content: str) -> tuple[str, list[dict]]:
    """Parse content and evaluate all checks for a policy.

    Returns (overall_status, [check_outcomes]).
    overall_status is one of: pass | fail | error
    """
    try:
        parsed = _parsers.parse(policy.parser_type, policy.parser_body, content)
    except Exception as exc:
        log.warning("compliance parse error", policy=policy.name, error=str(exc))
        return "error", [{"error": str(exc)}]

    rows: list[dict] = []
    if isinstance(parsed, list):
        rows = [r for r in parsed if isinstance(r, dict)]
    elif isinstance(parsed, dict):
        rows = [parsed]

    outcomes = [_evaluate_check(check, rows) for check in policy.checks]

    # Overall: fail if any non-info check fails; info failures don't escalate.
    failed_critical = any(o["status"] == "fail" and o["severity"] == "critical" for o in outcomes)
    failed_any = any(o["status"] == "fail" and o["severity"] != "info" for o in outcomes)
    overall = "fail" if (failed_critical or failed_any) else "pass"

    return overall, outcomes


def run_policy_for_devices(policy: CompliancePolicy, device_configs: list[tuple]) -> list[dict]:
    """Evaluate a policy against multiple (device_id, content) pairs.

    Returns list of result dicts ready to upsert into compliance_results.
    """
    now = datetime.now(tz=timezone.utc)
    results = []
    for device_id, content in device_configs:
        if content is None:
            results.append({
                "policy_id": policy.id,
                "device_id": device_id,
                "evaluated_at": now,
                "status": "skip",
                "detail": [],
            })
            continue
        status, outcomes = evaluate_policy(policy, content)
        results.append({
            "policy_id": policy.id,
            "device_id": device_id,
            "evaluated_at": now,
            "status": status,
            "detail": outcomes,
        })
    return results
