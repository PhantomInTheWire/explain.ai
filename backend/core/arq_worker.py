import asyncio
from datetime import datetime
from pathlib import Path

from arq import create_pool
from arq.connections import RedisSettings, ArqRedis
from arq.worker import Function
import convertapi

from core.config import settings
from core.logging import get_logger
from core.websocket import websocket_manager

log = get_logger(__name__)


# Job progress update helper for ARQ tasks
async def update_job_progress_arq(
    redis: ArqRedis,
    job_id: str,
    session_id: str,
    status: str,
    progress: int,
    error: str = "",
) -> None:
    """Update job progress in Redis and broadcast via WebSocket"""
    await redis.hset(
        f"job:{job_id}",
        mapping={
            "status": status,
            "progress": str(progress),
            "updated_at": datetime.utcnow().isoformat(),
            "error": error,
        },
    )
    # Broadcast update via WebSocket
    await websocket_manager.broadcast_job_update(
        session_id=session_id,
        job_id=job_id,
        status=status,
        progress=progress,
        error=error,
    )


async def complete_job_arq(
    redis: ArqRedis, job_id: str, session_id: str, result: dict
) -> None:
    """Mark job as complete and store result"""
    await update_job_progress_arq(redis, job_id, session_id, "completed", 100)
    await redis.set(f"job:{job_id}:result", result)
    await redis.expire(f"job:{job_id}:result", settings.session_ttl_seconds)
    # Broadcast completion with result
    await websocket_manager.broadcast_job_update(
        session_id=session_id,
        job_id=job_id,
        status="completed",
        progress=100,
        result=result,
    )


async def fail_job_arq(
    redis: ArqRedis, job_id: str, session_id: str, error: str
) -> None:
    """Mark job as failed"""
    await update_job_progress_arq(redis, job_id, session_id, "failed", 0, error)


# ARQ Task Functions
async def upload_pdf_task(
    ctx: dict,
    job_id: str,
    session_id: str,
    file_content: bytes,
    filename: str,
    content_type: str,
) -> dict:
    """ARQ task for PDF upload and processing"""
    redis: ArqRedis = ctx["redis"]
    log.info("upload started", job_id=job_id, session_id=session_id)

    try:
        await update_job_progress_arq(redis, job_id, session_id, "processing", 10)

        from apps.pdfops import upload_file

        result = await upload_file(session_id, file_content, filename, content_type)

        await complete_job_arq(redis, job_id, session_id, result)
        log.info("upload completed", job_id=job_id, session_id=session_id)
        return result
    except Exception as e:
        log.error("upload failed", job_id=job_id, error=str(e))
        await fail_job_arq(redis, job_id, session_id, str(e))
        raise


async def generate_presentation_task(
    ctx: dict, job_id: str, session_id: str, theme: str
) -> dict:
    """ARQ task for presentation generation"""
    redis: ArqRedis = ctx["redis"]
    log.info(
        "presentation generation started",
        job_id=job_id,
        session_id=session_id,
        theme=theme,
    )

    try:
        await update_job_progress_arq(redis, job_id, session_id, "processing", 10)

        from apps.ppt_generator import generate_presentation

        pptx_path = await generate_presentation(session_id, theme)

        await update_job_progress_arq(redis, job_id, session_id, "processing", 70)

        from core.storage import storage_manager

        pdf_path = storage_manager.get_output_path(session_id, "presentation.pdf")

        # ConvertAPI is sync, wrap in thread
        convertapi.api_secret = settings.convertapi_key
        await asyncio.to_thread(
            lambda: convertapi.convert(
                "pdf", {"File": str(pptx_path)}, from_format="pptx"
            ).save_files(str(pdf_path))
        )

        result = {
            "pptx_url": f"{settings.api_base_url}/api/sessions/{session_id}/files/presentation.pptx",
            "pdf_url": f"{settings.api_base_url}/api/sessions/{session_id}/files/presentation.pdf",
        }
        await complete_job_arq(redis, job_id, session_id, result)
        log.info("presentation completed", job_id=job_id, session_id=session_id)
        return result
    except Exception as e:
        log.error("presentation failed", job_id=job_id, error=str(e))
        await fail_job_arq(redis, job_id, session_id, str(e))
        raise


async def generate_video_task(ctx: dict, job_id: str, session_id: str) -> dict:
    """ARQ task for video generation"""
    redis: ArqRedis = ctx["redis"]
    log.info("video generation started", job_id=job_id, session_id=session_id)

    try:
        await update_job_progress_arq(redis, job_id, session_id, "processing", 10)

        from apps.promptops import generate_explanations

        explanations = await generate_explanations(session_id)

        await update_job_progress_arq(redis, job_id, session_id, "processing", 30)

        from apps.audiops import generate_audio_files
        import json

        await generate_audio_files(session_id, json.loads(explanations))

        await update_job_progress_arq(redis, job_id, session_id, "processing", 60)

        from core.storage import storage_manager
        from apps.videops import pdf_to_video

        pdf_path = storage_manager.get_output_path(session_id, "presentation.pdf")
        await pdf_to_video(session_id, pdf_path)

        result = {
            "video_url": f"{settings.api_base_url}/api/sessions/{session_id}/files/video.mp4"
        }
        await complete_job_arq(redis, job_id, session_id, result)
        log.info("video completed", job_id=job_id, session_id=session_id)
        return result
    except Exception as e:
        log.error("video failed", job_id=job_id, error=str(e))
        await fail_job_arq(redis, job_id, session_id, str(e))
        raise


# ARQ worker settings for default queue
class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 10
    job_timeout = 1800  # 30 minutes
    keep_result = 3600  # 1 hour
    queue_name = "default"

    functions: list[Function] = [
        Function(upload_pdf_task, name="upload_pdf_task"),
        Function(generate_presentation_task, name="generate_presentation_task"),
    ]


# ARQ worker settings for video queue
class VideoWorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 1  # Only 1 concurrent video job (CPU intensive)
    job_timeout = 1800  # 30 minutes
    keep_result = 3600  # 1 hour
    queue_name = "video"

    functions: list[Function] = [
        Function(generate_video_task, name="generate_video_task"),
    ]


# Helper to get ARQ pool for job enqueueing from FastAPI
_arq_pool: ArqRedis | None = None


async def get_arq_pool() -> ArqRedis:
    global _arq_pool
    if _arq_pool is None:
        _arq_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        log.info("arq pool created")
    return _arq_pool


async def close_arq_pool() -> None:
    global _arq_pool
    if _arq_pool is not None:
        await _arq_pool.close()
        _arq_pool = None
        log.info("arq pool closed")
