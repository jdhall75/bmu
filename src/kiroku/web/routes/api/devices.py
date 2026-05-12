"""API endpoints for devices.

POST /api/v1/devices/import
    Upsert devices from CSV. Accepts:
      - multipart/form-data  with a ``file`` field (file upload)
      - multipart/form-data  with a ``pasted`` field (raw CSV text)
      - Any other content-type: raw CSV body

    Returns JSON:
        {
          "ok": true,
          "created": 3,
          "updated": 1,
          "errors": 0,
          "rows": [
            {"line": 2, "name": "router-01", "action": "update", "ok": true, "message": "updated"},
            ...
          ]
        }

    When validation fails for any row, ok=false, created=0, updated=0, and
    errors shows how many rows had problems. Nothing is committed on failure.

curl examples:
    # Upload a file
    curl -s -X POST http://host/api/v1/devices/import -F file=@devices.csv

    # Pipe raw CSV
    curl -s -X POST http://host/api/v1/devices/import \
         -H "Content-Type: text/csv" --data-binary @devices.csv

    # Inline CSV
    curl -s -X POST http://host/api/v1/devices/import \
         -H "Content-Type: text/csv" \
         -d $'name,hostname,group\nrouter-01,10.0.0.1,core'
"""
from __future__ import annotations

from litestar import Router, post
from litestar.connection import Request
from sqlalchemy.orm import Session

from kiroku.web.deps import provide_db
from kiroku.web.import_devices import import_csv


@post("/import", dependencies={"db": provide_db})
async def import_devices(request: Request, db: Session) -> dict:
    content_type = request.headers.get("content-type", "")
    raw = ""

    if "multipart/form-data" in content_type:
        form = await request.form()
        upload = form.get("file")
        pasted = form.get("pasted") or ""
        if hasattr(upload, "read"):
            data = await upload.read()
            raw = data.decode("utf-8-sig", errors="replace")
        if not raw and pasted:
            raw = str(pasted).strip()
    else:
        body = await request.body()
        raw = body.decode("utf-8-sig", errors="replace").strip()

    if not raw:
        return {
            "ok": False,
            "created": 0,
            "updated": 0,
            "errors": 1,
            "rows": [],
            "error": "No CSV data provided. Send a multipart file field or a raw CSV body.",
        }

    try:
        results, created, updated = import_csv(db, raw)
    except Exception as exc:
        db.rollback()
        return {
            "ok": False,
            "created": 0,
            "updated": 0,
            "errors": 1,
            "rows": [],
            "error": f"{type(exc).__name__}: {exc}",
        }

    error_count = sum(1 for r in results if not r.ok)
    return {
        "ok": error_count == 0,
        "created": created,
        "updated": updated,
        "errors": error_count,
        "rows": [
            {
                "line": r.line,
                "name": r.name,
                "action": r.action,
                "ok": r.ok,
                "message": r.message,
            }
            for r in results
        ],
    }


router = Router(path="/devices", route_handlers=[import_devices])
