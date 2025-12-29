import asyncio
from datetime import datetime

from arq import create_pool
from arq.connections import RedisSettings, ArqRedis
from arq.worker import Function

from core.config import settings
from core.logging import get_logger

log = get_logger(__name__)


# ARQ worker settings for default queue
class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 10
    job_timeout = 1800  # 30 minutes (matching Celery)
    keep_result = 3600  # 1 hour
    queue_name = "default"

    # Task functions will be registered here after migration
    functions: list[Function] = []


# ARQ worker settings for video queue
class VideoWorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 1  # Only 1 concurrent video job (CPU intensive)
    job_timeout = 1800  # 30 minutes
    keep_result = 3600  # 1 hour
    queue_name = "video"

    # Video task functions will be registered here after migration
    functions: list[Function] = []


# Helper to get ARQ pool for job enqueueing from FastAPI
_arq_pool: ArqRedis | None = None


async def get_arq_pool() -> ArqRedis:
    global _arq_pool
    if _arq_pool is None:
        _arq_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _arq_pool


async def close_arq_pool() -> None:
    global _arq_pool
    if _arq_pool is not None:
        await _arq_pool.close()
        _arq_pool = None


# Job progress update helper for ARQ tasks
async def update_job_progress_arq(
    redis: ArqRedis, job_id: str, status: str, progress: int, error: str = ""
) -> None:
    """Update job progress in Redis for ARQ tasks"""
    await redis.hset(
        f"job:{job_id}",
        mapping={
            "status": status,
            "progress": str(progress),
            "updated_at": datetime.utcnow().isoformat(),
            "error": error,
        },
    )
