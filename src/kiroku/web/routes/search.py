from __future__ import annotations

from litestar import Router, get
from litestar.response import Template
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from kiroku.models import DeviceGroup
from kiroku.web.deps import provide_db

PAGE_SIZE = 50

# Subquery fragments reused in both search modes.
_GROUP_NAMES_SUBQ = """
    (SELECT string_agg(dg.name, ', ' ORDER BY dg.name)
     FROM device_group_memberships dgm
     JOIN device_groups dg ON dg.id = dgm.device_group_id
     WHERE dgm.device_id = d.id)
"""
_GROUP_FILTER = """
    AND EXISTS (
        SELECT 1 FROM device_group_memberships dgm
        WHERE dgm.device_id = d.id AND dgm.device_group_id = :gid
    )
"""


def _extract_context(content: str, terms: list[str], context: int = 3) -> list[dict]:
    """Return line-context blocks for all matching lines in content."""
    if not content or not terms:
        return []
    lines = content.splitlines()
    lower_terms = [t.lower() for t in terms]
    hits: set[int] = set()
    for i, line in enumerate(lines):
        ll = line.lower()
        if any(t in ll for t in lower_terms):
            hits.update(range(max(0, i - context), min(len(lines), i + context + 1)))

    blocks: list[list[int]] = []
    block: list[int] = []
    for i in sorted(hits):
        if block and i > block[-1] + 1:
            blocks.append(block)
            block = []
        block.append(i)
    if block:
        blocks.append(block)

    return [
        {
            "start_line": b[0] + 1,
            "lines": [
                {
                    "num": j + 1,
                    "text": lines[j],
                    "hit": any(t in lines[j].lower() for t in lower_terms),
                }
                for j in b
            ],
        }
        for b in blocks
    ]


@get("/", dependencies={"db": provide_db})
async def search_configs(
    db: Session,
    q: str = "",
    group_id: str = "",
    mode: str = "fts",
    context_lines: int = 3,
) -> Template:
    groups = db.scalars(select(DeviceGroup).order_by(DeviceGroup.name)).all()
    results: list[dict] = []

    q = q.strip()
    if q:
        gid = int(group_id) if group_id.isdigit() else 0
        params: dict = {"q": q, "limit": PAGE_SIZE}

        if mode == "exact":
            params["pattern"] = f"%{q}%"
            where_group = _GROUP_FILTER if gid else ""
            rows = (
                db.execute(
                    text(f"""
                SELECT dc.device_id, dc.captured_at, dc.content,
                       d.name AS device_name,
                       {_GROUP_NAMES_SUBQ} AS group_name
                FROM device_configs dc
                JOIN devices d ON d.id = dc.device_id
                WHERE dc.content ILIKE :pattern
                  {where_group}
                ORDER BY dc.captured_at DESC
                LIMIT :limit
            """),
                    {**params, **({"gid": gid} if gid else {})},
                )
                .mappings()
                .all()
            )
            terms = [q]
        else:
            where_group = _GROUP_FILTER if gid else ""
            rows = (
                db.execute(
                    text(f"""
                SELECT dc.device_id, dc.captured_at, dc.content,
                       d.name AS device_name,
                       {_GROUP_NAMES_SUBQ} AS group_name,
                       ts_headline('simple', dc.content,
                                   websearch_to_tsquery('simple', :q),
                                   'MaxWords=30, MinWords=10') AS headline
                FROM device_configs dc
                JOIN devices d ON d.id = dc.device_id
                WHERE dc.content_fts @@ websearch_to_tsquery('simple', :q)
                  {where_group}
                ORDER BY dc.captured_at DESC
                LIMIT :limit
            """),
                    {**params, **({"gid": gid} if gid else {})},
                )
                .mappings()
                .all()
            )
            terms = q.split()

        for row in rows:
            results.append(
                {
                    "device_id": row["device_id"],
                    "device_name": row["device_name"],
                    "group_name": row["group_name"],
                    "captured_at": row["captured_at"],
                    "headline": row.get("headline"),
                    "blocks": _extract_context(
                        row["content"] or "", terms, context_lines
                    ),
                }
            )

    return Template(
        template_name="search.html",
        context={
            "q": q,
            "group_id": group_id,
            "mode": mode,
            "context_lines": context_lines,
            "groups": groups,
            "results": results,
        },
    )


router = Router(path="/search", route_handlers=[search_configs])
