from kiroku.config import get_settings
from litestar.response import Redirect


def redir(path: str) -> Redirect:
    s = get_settings()
    return Redirect(s.root_path.rstrip("/") + path)
