import json
import logging
import os
from contextlib import asynccontextmanager

import convertapi
from fastapi import FastAPI, UploadFile, File, Request, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend.apps.audiops import generate_audio_files
from backend.apps.pdfops import upload_file
from backend.apps.ppt_generator import generate_presentation
from backend.apps.promptops import generate_explanations
from backend.apps.videops import pdf_to_video
from backend.core.config import settings
from backend.core.session import session_manager
from backend.core.jobs import JobManager, JobStatus, JobType
from backend.core.vectorstore import vectorstore_manager
from backend.core.storage import storage_manager
from backend.core.cleanup import cleanup_task
from backend.core.middleware import SessionMiddleware, get_session_id

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await session_manager.initialize()
    await vectorstore_manager.initialize()
    await cleanup_task.start()
    logger.info("Application started")
    yield
    await cleanup_task.stop()
    vectorstore_manager.close()
    await session_manager.close()
    logger.info("Application stopped")


app = FastAPI(title="Vedanta API", version="2.0", lifespan=lifespan)

app.add_middleware(SessionMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"title": "Project Vedanta", "version": "2.0", "status": "multi-user"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/ready")
async def ready():
    try:
        await session_manager.redis.ping()
        return {"status": "ready", "redis": "connected", "weaviate": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Not ready: {e}")


# Session Management
@app.post("/api/sessions")
async def create_session():
    session_id = await session_manager.create_session()
    storage_manager.create_session_directories(session_id)
    return {"session_id": session_id, "ttl": settings.session_ttl_seconds}


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    jobs = await session_manager.get_session_jobs(session_id)
    files = storage_manager.list_output_files(session_id)
    return {"session": session, "jobs": jobs, "files": files}


# Job Management
@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    job_manager = JobManager(session_manager.redis)
    job = await job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    result = await job_manager.get_job_result(job_id)
    return {"job": job, "result": result}


# Pipeline Endpoints
async def run_upload_job(
    job_id: str, session_id: str, file_content: bytes, filename: str, content_type: str
):
    job_manager = JobManager(session_manager.redis)
    try:
        await job_manager.update_job_status(job_id, JobStatus.PROCESSING, progress=10)

        from io import BytesIO
        from fastapi import UploadFile as UP

        file_obj = BytesIO(file_content)
        file_obj.name = filename

        class FakeUploadFile:
            def __init__(self, content, name, ctype):
                self._content = content
                self.filename = name
                self.content_type = ctype

            async def read(self):
                return self._content

        fake_file = FakeUploadFile(file_content, filename, content_type)
        result = await upload_file(session_id, fake_file)
        await job_manager.complete_job(job_id, result)
    except Exception as e:
        logger.error(f"Upload job failed: {e}")
        await job_manager.fail_job(job_id, str(e))


@app.post("/api/upload_pdf/")
async def upload_pdf_endpoint(
    request: Request, background_tasks: BackgroundTasks, file: UploadFile = File(...)
):
    session_id = get_session_id(request)
    job_manager = JobManager(session_manager.redis)

    job_id, error = await job_manager.create_job(session_id, JobType.UPLOAD_PDF)
    if error:
        raise HTTPException(status_code=429, detail=error)

    file_content = await file.read()
    background_tasks.add_task(
        run_upload_job,
        job_id,
        session_id,
        file_content,
        file.filename,
        file.content_type,
    )

    return {"job_id": job_id, "status": "pending"}


async def run_presentation_job(job_id: str, session_id: str, theme: str):
    job_manager = JobManager(session_manager.redis)
    try:
        await job_manager.update_job_status(job_id, JobStatus.PROCESSING, progress=10)

        pptx_path = await generate_presentation(session_id, theme)
        await job_manager.update_job_status(job_id, JobStatus.PROCESSING, progress=70)

        pdf_path = storage_manager.get_output_path(session_id, "presentation.pdf")
        convertapi.api_secret = settings.convertapi_key
        convertapi.convert(
            "pdf", {"File": str(pptx_path)}, from_format="pptx"
        ).save_files(str(pdf_path))

        result = {
            "pptx_url": f"{settings.api_base_url}/api/sessions/{session_id}/files/presentation.pptx",
            "pdf_url": f"{settings.api_base_url}/api/sessions/{session_id}/files/presentation.pdf",
        }
        await job_manager.complete_job(job_id, result)
    except Exception as e:
        logger.error(f"Presentation job failed: {e}")
        await job_manager.fail_job(job_id, str(e))


@app.post("/api/get_presentation/")
async def get_presentation_endpoint(
    request: Request, background_tasks: BackgroundTasks
):
    session_id = get_session_id(request)
    job_manager = JobManager(session_manager.redis)

    body = (
        await request.json()
        if request.headers.get("content-type") == "application/json"
        else {}
    )
    theme = body.get("theme", "Theme1")

    job_id, error = await job_manager.create_job(
        session_id, JobType.GENERATE_PRESENTATION, {"theme": theme}
    )
    if error:
        raise HTTPException(status_code=429, detail=error)

    background_tasks.add_task(run_presentation_job, job_id, session_id, theme)

    return {"job_id": job_id, "status": "pending"}


async def run_video_job(job_id: str, session_id: str):
    job_manager = JobManager(session_manager.redis)
    try:
        await job_manager.update_job_status(job_id, JobStatus.PROCESSING, progress=10)

        explanations = await generate_explanations(session_id)
        await job_manager.update_job_status(job_id, JobStatus.PROCESSING, progress=30)

        await generate_audio_files(session_id, json.loads(explanations))
        await job_manager.update_job_status(job_id, JobStatus.PROCESSING, progress=60)

        pdf_path = storage_manager.get_output_path(session_id, "presentation.pdf")
        await pdf_to_video(session_id, pdf_path)

        result = {
            "video_url": f"{settings.api_base_url}/api/sessions/{session_id}/files/video.mp4"
        }
        await job_manager.complete_job(job_id, result)
    except Exception as e:
        logger.error(f"Video job failed: {e}")
        await job_manager.fail_job(job_id, str(e))


@app.post("/api/generate_video/")
async def generate_video_endpoint(request: Request, background_tasks: BackgroundTasks):
    session_id = get_session_id(request)
    job_manager = JobManager(session_manager.redis)

    job_id, error = await job_manager.create_job(session_id, JobType.GENERATE_VIDEO)
    if error:
        raise HTTPException(status_code=429, detail=error)

    background_tasks.add_task(run_video_job, job_id, session_id)

    return {"job_id": job_id, "status": "pending"}


# File Serving
@app.get("/api/sessions/{session_id}/files/{filename}")
async def get_session_file(session_id: str, filename: str):
    if not await session_manager.validate_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    file_path = storage_manager.get_file(session_id, filename)
    if not file_path:
        raise HTTPException(status_code=404, detail="File not found")

    media_types = {
        ".pdf": "application/pdf",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".mp4": "video/mp4",
        ".mp3": "audio/mpeg",
    }
    ext = file_path.suffix.lower()

    return FileResponse(
        str(file_path), media_type=media_types.get(ext, "application/octet-stream")
    )


# Legacy endpoints for backwards compatibility
@app.get("/api/get/{filename}")
async def get_file_legacy(request: Request, filename: str):
    session_id = get_session_id(request)
    return await get_session_file(session_id, filename)
