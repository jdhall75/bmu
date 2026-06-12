from kiroku.config import get_settings
from litestar.response import Redirect

from kiroku.logging import get_logger

log = get_logger()


def redir(path: str) -> Redirect:
    s = get_settings()
    path = s.root_path.rstrip("/") + path
    # return Redirect(s.root_path.rstrip("/") + path)
    return Redirect(path)
