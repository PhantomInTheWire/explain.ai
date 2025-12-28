from celery import Celery

from core.config import settings
from core.logging import setup_logging, get_logger

setup_logging(debug=settings.debug)
log = get_logger(__name__)

celery_app = Celery(
    "explainai",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["apps.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=1800,  # 30 min hard limit
    task_soft_time_limit=1500,  # 25 min soft limit
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_routes={
        "apps.tasks.generate_video_task": {"queue": "video"},
    },
    task_default_queue="default",
)
