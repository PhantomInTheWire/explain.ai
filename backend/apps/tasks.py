import json
import asyncio
from pathlib import Path

import convertapi

from core.celery import celery_app
from core.config import settings
from core.logging import get_logger

log = get_logger(__name__)


def get_sync_redis():
    import redis

    return redis.from_url(settings.redis_url, decode_responses=True)


def update_job_progress(job_id: str, status: str, progress: int, error: str = ""):
    from datetime import datetime

    redis_client = get_sync_redis()
    redis_client.hset(
        f"job:{job_id}",
        mapping={
            "status": status,
            "progress": str(progress),
            "updated_at": datetime.utcnow().isoformat(),
            "error": error,
        },
    )


def complete_job(job_id: str, result: dict):
    update_job_progress(job_id, "completed", 100)
    redis_client = get_sync_redis()
    redis_client.set(f"job:{job_id}:result", json.dumps(result))
    redis_client.expire(f"job:{job_id}:result", settings.session_ttl_seconds)


def fail_job(job_id: str, error: str):
    update_job_progress(job_id, "failed", 0, error)


@celery_app.task(bind=True, name="apps.tasks.upload_pdf_task")
def upload_pdf_task(
    self,
    job_id: str,
    session_id: str,
    file_content: bytes,
    filename: str,
    content_type: str,
):
    log.info("upload started", job_id=job_id, session_id=session_id)
    try:
        update_job_progress(job_id, "processing", 10)

        from apps.pdfops import upload_file_sync

        result = upload_file_sync(session_id, file_content, filename, content_type)

        complete_job(job_id, result)
        log.info("upload completed", job_id=job_id, session_id=session_id)
    except Exception as e:
        log.error("upload failed", job_id=job_id, error=str(e))
        fail_job(job_id, str(e))
        raise


@celery_app.task(bind=True, name="apps.tasks.generate_presentation_task")
def generate_presentation_task(self, job_id: str, session_id: str, theme: str):
    log.info(
        "presentation generation started",
        job_id=job_id,
        session_id=session_id,
        theme=theme,
    )
    try:
        update_job_progress(job_id, "processing", 10)

        from apps.ppt_generator import generate_presentation_sync

        pptx_path = generate_presentation_sync(session_id, theme)

        update_job_progress(job_id, "processing", 70)

        from core.storage import storage_manager

        pdf_path = storage_manager.get_output_path(session_id, "presentation.pdf")

        convertapi.api_secret = settings.convertapi_key
        convertapi.convert(
            "pdf", {"File": str(pptx_path)}, from_format="pptx"
        ).save_files(str(pdf_path))

        result = {
            "pptx_url": f"{settings.api_base_url}/api/sessions/{session_id}/files/presentation.pptx",
            "pdf_url": f"{settings.api_base_url}/api/sessions/{session_id}/files/presentation.pdf",
        }
        complete_job(job_id, result)
        log.info("presentation completed", job_id=job_id, session_id=session_id)
    except Exception as e:
        log.error("presentation failed", job_id=job_id, error=str(e))
        fail_job(job_id, str(e))
        raise


@celery_app.task(
    bind=True, name="apps.tasks.generate_video_task", queue="video"
)
def generate_video_task(self, job_id: str, session_id: str):
    log.info("video generation started", job_id=job_id, session_id=session_id)
    try:
        update_job_progress(job_id, "processing", 10)

        from apps.promptops import generate_explanations_sync

        explanations = generate_explanations_sync(session_id)

        update_job_progress(job_id, "processing", 30)

        from apps.audiops import generate_audio_files_sync

        generate_audio_files_sync(session_id, json.loads(explanations))

        update_job_progress(job_id, "processing", 60)

        from core.storage import storage_manager
        from apps.videops import pdf_to_video_sync

        pdf_path = storage_manager.get_output_path(session_id, "presentation.pdf")
        pdf_to_video_sync(session_id, pdf_path)

        result = {
            "video_url": f"{settings.api_base_url}/api/sessions/{session_id}/files/video.mp4"
        }
        complete_job(job_id, result)
        log.info("video completed", job_id=job_id, session_id=session_id)
    except Exception as e:
        log.error("video failed", job_id=job_id, error=str(e))
        fail_job(job_id, str(e))
        raise
