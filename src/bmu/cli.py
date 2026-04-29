import subprocess
import sys

import click

from bmu.config import get_settings
from bmu.logging import configure_logging


@click.group()
def main() -> None:
    """BackMeUp control CLI."""


@main.command()
def serve() -> None:
    """Run the Litestar web app via uvicorn."""
    configure_logging()
    s = get_settings()
    import uvicorn

    uvicorn.run("bmu.web.app:app", host=s.web_host, port=s.web_port, log_level=s.log_level.lower())


@main.command()
def scheduler() -> None:
    """Run the scheduler process."""
    from bmu.scheduler import run_scheduler

    run_scheduler()


@main.command()
def worker() -> None:
    """Run a worker process."""
    from bmu.worker import run_worker

    run_worker()


@main.command()
def recorder() -> None:
    """Run the recorder process (writes git + updates runs)."""
    from bmu.recorder import run_recorder

    run_recorder()


@main.command()
def migrate() -> None:
    """Run alembic upgrade head."""
    rc = subprocess.call(["alembic", "upgrade", "head"])
    sys.exit(rc)


if __name__ == "__main__":
    main()
