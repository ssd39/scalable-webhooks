"""
RQ worker entry-point.

On macOS, RQ's default Worker forks a child process which crashes when
Objective-C / CoreFoundation libraries (e.g. those pulled in by langchain-anthropic)
are loaded before fork(). SimpleWorker avoids this by running jobs in the same
process without forking — safe for both development (macOS) and production (Linux).

Run locally:
    python -m app.worker.listener

Docker (see docker-compose.yml):
    command: python -m app.worker.listener
"""

import logging
import sys
import platform

from rq import SimpleWorker, Worker

from app.config import settings
from app.services.redis_client import get_redis_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def main() -> None:
    redis_conn = get_redis_connection()
    queues = [settings.WEBHOOK_QUEUE_NAME]

    # Use SimpleWorker on macOS to avoid fork() crashes with Obj-C runtime.
    # On Linux (Docker / production), use the standard Worker which forks.
    if platform.system() == "Darwin":
        logger.info("macOS detected – using SimpleWorker (no-fork mode)")
        worker_cls = SimpleWorker
    else:
        worker_cls = Worker

    logger.info("Starting %s – listening on queues: %s", worker_cls.__name__, queues)
    worker = worker_cls(queues=queues, connection=redis_conn)
    worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()
