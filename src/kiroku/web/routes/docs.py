"""Serve documentation pages as rendered HTML fragments for the help modal."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import markdown
from litestar import Router, get

# Docs live alongside the package so they're always available after install.
DOCS_ROOT = Path(__file__).parents[1] / "docs"

_MD = markdown.Markdown(
    extensions=["tables", "fenced_code", "toc", "attr_list"],
    output_format="html",
)

_SAFE_PAGE = re.compile(r"^[a-z0-9_-]+$")


@lru_cache(maxsize=64)
def _render(page: str) -> str:
    path = DOCS_ROOT / f"{page}.md"
    if not path.exists():
        return "<p>Documentation page not found.</p>"
    _MD.reset()
    return _MD.convert(path.read_text(encoding="utf-8"))


@get("/docs/{page:str}", media_type="text/html")
async def get_doc(page: str) -> str:
    if not _SAFE_PAGE.match(page):
        return "<p>Invalid page name.</p>"
    return f'<div class="prose">{_render(page)}</div>'


router = Router(path="/", route_handlers=[get_doc])
