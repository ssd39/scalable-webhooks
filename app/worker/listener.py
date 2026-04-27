"""
RQ worker entry-point.

Run locally:
    python -m app.worker.listener

Docker (see docker-compose.yml):
    command: python -m app.worker.listener
"""

import logging
import sys

from rq import Worker

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
    logger.info("Starting RQ worker – listening on queues: %s", queues)

    worker = Worker(queues=queues, connection=redis_conn)
    worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()
