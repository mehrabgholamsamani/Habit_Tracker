"""Serialized release tasks used by the container entrypoint."""

import argparse
import subprocess
import sys
import logging
import time

from sqlalchemy import text

from .database import engine
from .logging_config import configure_logging


_STARTUP_LOCK_ID = 742_019_884
logger = logging.getLogger(__name__)


def _run(command: list[str]) -> None:
    # A session advisory lock prevents multiple replicas from changing or
    # seeding the schema concurrently during a rolling deployment.
    task = "migration" if command[0] == "alembic" else "seed"
    started = time.monotonic()
    logger.info("Release task starting", extra={"event": "startup_task_started", "task": task})
    with engine.connect() as connection:
        connection.execute(text("SELECT pg_advisory_lock(:lock_id)"), {"lock_id": _STARTUP_LOCK_ID})
        try:
            subprocess.run(command, check=True)
            logger.info(
                "Release task completed",
                extra={
                    "event": "startup_task_completed",
                    "task": task,
                    "outcome": "success",
                    "duration_ms": round((time.monotonic() - started) * 1000, 2),
                },
            )
        except subprocess.CalledProcessError:
            logger.error(
                "Release task failed",
                extra={
                    "event": "startup_task_failed",
                    "task": task,
                    "outcome": "error",
                    "duration_ms": round((time.monotonic() - started) * 1000, 2),
                },
            )
            raise
        finally:
            connection.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": _STARTUP_LOCK_ID}
            )


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("task", choices=("migrate", "seed"))
    task = parser.parse_args().task
    command = ["alembic", "upgrade", "head"] if task == "migrate" else [sys.executable, "-m", "app.seed"]
    _run(command)


if __name__ == "__main__":
    main()
