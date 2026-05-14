from collections.abc import Iterator

from litestar.connection import Request
from sqlalchemy.orm import Session

from kiroku.db import SessionLocal
from kiroku.web.auth import User


def provide_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def provide_user(request: Request) -> User | None:
    return getattr(request, "user", None)
