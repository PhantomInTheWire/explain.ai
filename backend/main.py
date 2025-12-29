from contextlib import asynccontextmanager

from fastapi import (
    FastAPI,
    UploadFile,
    File,
    Request,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from core.config import settings
from core.logging import setup_logging, get_logger
from core.session import session_manager
from core.jobs import JobManager, JobType
from core.vectorstore import vectorstore_manager
from core.storage import storage_manager
from core.cleanup import cleanup_task
from core.middleware import SessionMiddleware, get_session_id
from core.websocket import websocket_manager
from core.arq_worker import get_arq_pool, close_arq_pool

setup_logging(debug=settings.debug)
log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await session_manager.initialize()
    await vectorstore_manager.initialize()
    await get_arq_pool()  # Initialize ARQ pool
    await cleanup_task.start()
    log.info("application started")
    yield
    await cleanup_task.stop()
    await close_arq_pool()  # Close ARQ pool
    await vectorstore_manager.close()
    await session_manager.close()
    log.info("application stopped")


app = FastAPI(title="ExplainAI API", version="2.0", lifespan=lifespan)

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
    return {"title": "Project ExplainAI", "version": "2.0", "status": "multi-user"}


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


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    job_manager = JobManager(session_manager.redis)
    job = await job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    result = await job_manager.get_job_result(job_id)
    return {"job": job, "result": result}


@app.post("/api/upload_pdf/")
async def upload_pdf_endpoint(request: Request, file: UploadFile = File(...)):
    session_id = get_session_id(request)
    job_manager = JobManager(session_manager.redis)

    job_id, error = await job_manager.create_job(session_id, JobType.UPLOAD_PDF)
    if error:
        raise HTTPException(status_code=429, detail=error)

    file_content = await file.read()

    # Enqueue ARQ task
    arq_pool = await get_arq_pool()
    await arq_pool.enqueue_job(
        "upload_pdf_task",
        job_id,
        session_id,
        file_content,
        file.filename or "uploaded.pdf",
        file.content_type or "application/pdf",
    )

    return {"job_id": job_id, "status": "pending"}


@app.post("/api/get_presentation/")
async def get_presentation_endpoint(request: Request):
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

    # Enqueue ARQ task
    arq_pool = await get_arq_pool()
    await arq_pool.enqueue_job("generate_presentation_task", job_id, session_id, theme)

    return {"job_id": job_id, "status": "pending"}


@app.post("/api/generate_video/")
async def generate_video_endpoint(request: Request):
    session_id = get_session_id(request)
    job_manager = JobManager(session_manager.redis)

    job_id, error = await job_manager.create_job(session_id, JobType.GENERATE_VIDEO)
    if error:
        raise HTTPException(status_code=429, detail=error)

    # Enqueue ARQ task on video queue
    arq_pool = await get_arq_pool()
    await arq_pool.enqueue_job(
        "generate_video_task",
        job_id,
        session_id,
        _queue_name="video",  # Route to video worker queue
    )

    return {"job_id": job_id, "status": "pending"}


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


@app.get("/api/get/{filename}")
async def get_file_legacy(request: Request, filename: str):
    session_id = get_session_id(request)
    return await get_session_file(session_id, filename)


@app.websocket("/api/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time job updates"""
    await websocket_manager.connect(session_id, websocket)
    log.debug("websocket connection established", session_id=session_id)

    try:
        # Keep connection alive and listen for messages (currently just ping/pong)
        while True:
            # Wait for any message from client (ping to keep alive)
            try:
                data = await websocket.receive_text()
                # Echo back for ping/pong
                if data == "ping":
                    await websocket.send_text("pong")
            except WebSocketDisconnect:
                break
    except Exception as e:
        log.error("websocket error", session_id=session_id, error=str(e))
    finally:
        await websocket_manager.disconnect(session_id, websocket)
        log.debug("websocket connection closed", session_id=session_id)
