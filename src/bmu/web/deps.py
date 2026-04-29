from collections.abc import Iterator

from sqlalchemy.orm import Session

from bmu.db import SessionLocal


def provide_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
