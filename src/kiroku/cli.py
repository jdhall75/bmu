import subprocess
import sys

import click

from kiroku.config import get_settings
from kiroku.logging import configure_logging, get_logger

logger = get_logger(__name__)


@click.group()
def main() -> None:
    """Kiroku control CLI."""


@main.command()
def serve() -> None:
    """Run the Litestar web app via uvicorn."""
    s = get_settings()
    logger.info("this is a test")
    import uvicorn

    uvicorn.run(
        "kiroku.web.app:app",
        host=s.web_host,
        port=s.web_port,
        log_config=None,
        reload=s.reload,
        workers=s.web_workers,
    )


@main.command()
def scheduler() -> None:
    """Run the scheduler process."""
    from kiroku.scheduler import run_scheduler

    run_scheduler()


@main.command()
def worker() -> None:
    """Run a worker process."""
    from kiroku.worker import run_worker

    run_worker()


@main.command()
def recorder() -> None:
    """Run the recorder process (writes git + updates runs)."""
    from kiroku.recorder import run_recorder

    run_recorder()


@main.command()
def migrate() -> None:
    """Run alembic upgrade head."""
    rc = subprocess.call(["alembic", "upgrade", "head"])
    sys.exit(rc)


if __name__ == "__main__":
    main()
