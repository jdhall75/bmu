"""Serve documentation pages — fragment endpoint for internal use, full page for help window."""

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

_HELP_SHELL = """\
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Kiroku Help</title>
  <link rel="stylesheet" href="/static/pico.min.css">
  <link rel="stylesheet" href="/static/app.css">
  <script>
  (function() {{
    function getCookie(name) {{
      var row = document.cookie.split('; ').find(function(r) {{ return r.startsWith(name + '='); }});
      return row ? row.split('=')[1] : null;
    }}
    var saved = getCookie('kiroku_theme');
    var theme = saved || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    document.documentElement.setAttribute('data-theme', theme);
  }})();
  </script>
</head>
<body>
  <main class="container">
    <div class="prose">
{content}
    </div>
  </main>
</body>
</html>"""


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


@get("/help/{page:str}", media_type="text/html")
async def get_help_page(page: str) -> str:
    if not _SAFE_PAGE.match(page):
        content = "<p>Invalid page name.</p>"
    else:
        content = _render(page)
    return _HELP_SHELL.format(content=content)


router = Router(path="/", route_handlers=[get_doc, get_help_page])
