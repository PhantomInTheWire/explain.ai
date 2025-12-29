# Backend - ExplainAI

The backend is built with FastAPI and uses ARQ (Async Redis Queue) for background job processing.

## Architecture

### Async-First Design

The entire backend is built using native async/await patterns:
- FastAPI async endpoints
- ARQ for async task queue processing
- Native async clients for all external services (LangChain, Weaviate, Google TTS)
- WebSocket for real-time progress updates

### Background Processing with ARQ

ARQ provides async task processing with two specialized workers:

#### 1. Default Worker (`core.arq_worker.WorkerSettings`)
Handles most background tasks:
- PDF extraction and processing
- Content chunking and vectorization
- Prompt generation with LangChain
- PowerPoint generation
- Audio generation with Google TTS

Configuration:
- Queue: `arq:queue` (default)
- Max concurrent jobs: `ARQ_MAX_JOBS` (default: 10)
- Job timeout: 3600 seconds

#### 2. Video Worker (`core.arq_worker.VideoWorkerSettings`)
Specialized for video encoding:
- Video generation from slides and audio
- GPU-accelerated encoding
- Memory-intensive operations

Configuration:
- Queue: `arq:queue:video`
- Max concurrent jobs: `ARQ_VIDEO_MAX_JOBS` (default: 1)
- Job timeout: 3600 seconds

### Task Flow

```
User Upload
    ↓
FastAPI Endpoint → Enqueue ARQ Job
    ↓
Default Worker:
  1. Extract PDF → Vectorize → Generate Prompts
  2. Generate PowerPoint
  3. Generate Audio for each slide
    ↓
Video Worker:
  4. Generate Video (GPU-accelerated)
    ↓
WebSocket → Send Progress Updates
    ↓
Complete → User Downloads Files
```

## Running the Backend

### With Docker (Recommended)

```bash
docker-compose up --build
```

This starts:
- FastAPI server (port 8000)
- Redis (port 6379)
- Weaviate (port 8080)
- ARQ default worker
- ARQ video worker

### Local Development

1. **Install dependencies:**
   ```bash
   uv sync
   ```

2. **Set up environment:**
   ```bash
   cp ../.env.example .env
   # Edit .env with your API keys
   ```

3. **Start services:**
   ```bash
   # Terminal 1: FastAPI server
   uv run uvicorn main:app --reload --port 8000

   # Terminal 2: Default ARQ worker
   uv run arq core.arq_worker.WorkerSettings

   # Terminal 3: Video ARQ worker
   uv run arq core.arq_worker.VideoWorkerSettings
   ```

4. **Redis and Weaviate:**
   ```bash
   # Using Docker for services only
   docker-compose up redis weaviate
   ```

## Configuration

### Environment Variables

```bash
# Required API Keys
GOOGLE_API_KEY=your-google-api-key-here
CONVERTAPI_KEY=your-convertapi-key-here
GOOGLE_APPLICATION_CREDENTIALS=/app/credentials.json

# Redis & Weaviate
REDIS_URL=redis://localhost:6379
WEAVIATE_URL=http://localhost:8080

# ARQ Worker Configuration
ARQ_MAX_JOBS=10              # Default worker concurrency
ARQ_VIDEO_MAX_JOBS=1         # Video worker concurrency

# GPU Acceleration (Video Encoding)
VIDEO_GPU_CODEC=h264_videotoolbox  # Options: h264_videotoolbox, h264_nvenc, h264_qsv, libx264

# Session Management
SESSION_TTL_SECONDS=3600
DATA_DIR=./data/sessions
CLEANUP_INTERVAL_SECONDS=300
```

### GPU Codec Selection

The `VIDEO_GPU_CODEC` environment variable controls video encoding:

| Platform | Codec | GPU | Performance |
|----------|-------|-----|-------------|
| macOS | `h264_videotoolbox` | Apple Silicon/AMD | Excellent |
| Linux (NVIDIA) | `h264_nvenc` | NVIDIA GPU | Excellent |
| Linux/Windows (Intel) | `h264_qsv` | Intel iGPU | Good |
| Fallback | `libx264` | CPU only | Slow |

**Default:** `h264_videotoolbox` on macOS, `libx264` elsewhere.

### Scaling Workers

Adjust concurrency based on your hardware:

```bash
# High-performance server (16+ cores, GPU)
ARQ_MAX_JOBS=20
ARQ_VIDEO_MAX_JOBS=2

# Development machine (4-8 cores)
ARQ_MAX_JOBS=5
ARQ_VIDEO_MAX_JOBS=1

# Low-resource environment
ARQ_MAX_JOBS=2
ARQ_VIDEO_MAX_JOBS=1
```

## Project Structure

```
backend/
├── apps/                   # Application modules
│   ├── audiops.py         # Audio generation (async TTS)
│   ├── pdfops.py          # PDF extraction & vectorization
│   ├── promptops.py       # LangChain prompt generation
│   ├── ppt_generator.py   # PowerPoint creation
│   └── videops.py         # Video generation (GPU-accelerated)
│
├── core/                   # Core utilities
│   ├── arq_worker.py      # ARQ worker configuration & tasks
│   ├── websocket.py       # WebSocket connection manager
│   ├── config.py          # Settings & configuration
│   ├── session.py         # Session management
│   ├── storage.py         # File storage utilities
│   ├── vectorstore.py     # Weaviate integration
│   └── logging.py         # Structured logging
│
├── theme_pptx/            # PowerPoint themes
│   ├── Theme1.pptx
│   ├── Theme2.pptx
│   ├── Theme3.pptx
│   └── Theme4.pptx
│
├── main.py                # FastAPI application
├── pyproject.toml         # Python dependencies
└── Dockerfile             # Backend container
```

## API Endpoints

### HTTP Endpoints

- `POST /api/upload` - Upload PDF file
- `POST /api/convert` - Convert PDF to PowerPoint
- `POST /api/generate` - Generate presentation with custom options
- `GET /api/download/{session_id}/{file_type}` - Download generated files
- `GET /api/sessions/{session_id}` - Get session status

### WebSocket Endpoint

- `WS /api/ws/{session_id}` - Real-time job progress updates

Example WebSocket message:
```json
{
  "job_id": "abc123",
  "status": "processing",
  "step": "generating_audio",
  "progress": 45,
  "message": "Generating audio for slide 3 of 10"
}
```

## Dependencies

Key packages:
- `fastapi` - Web framework
- `arq` - Async task queue
- `redis` - Redis client
- `weaviate-client` - Vector database (async)
- `langchain-google-genai` - LLM integration
- `google-cloud-texttospeech` - TTS (async)
- `python-pptx` - PowerPoint generation
- `pdfplumber` - PDF extraction
- `moviepy` - Video generation

See `pyproject.toml` for complete list.

## Development Notes

### Async Patterns

All I/O operations use async/await:
```python
# External API calls
result = await llm.ainvoke(prompt)
audio = await tts_client.synthesize_speech_async(request)

# Database operations
await weaviate_client.collections.get("Documents").query.fetch_objects()

# Blocking operations (wrapped in thread pool)
result = await asyncio.to_thread(sync_function, args)
```

### ARQ Job Enqueuing

```python
from core.config import get_redis_pool

redis = await get_redis_pool()
job = await redis.enqueue_job(
    'generate_presentation',
    session_id='abc123',
    options={'theme': 1}
)
```

### WebSocket Progress Updates

```python
from core.websocket import manager

await manager.send_progress(
    session_id='abc123',
    status='processing',
    progress=50,
    message='Halfway done'
)
```

## Monitoring

### Check ARQ Job Status

```bash
# Using redis-cli
redis-cli LLEN arq:queue           # Default queue length
redis-cli LLEN arq:queue:video     # Video queue length
```

### Check Worker Health

Workers log to stdout. In Docker:
```bash
docker-compose logs -f arq-worker
docker-compose logs -f arq-video-worker
```

### WebSocket Connections

Active connections tracked in `core.websocket.ConnectionManager`:
```python
print(f"Active connections: {len(manager.active_connections)}")
```

## Troubleshooting

### Workers not processing jobs

1. Check Redis connection:
   ```bash
   docker-compose logs redis
   ```

2. Check worker logs:
   ```bash
   docker-compose logs arq-worker
   docker-compose logs arq-video-worker
   ```

3. Verify environment variables are set correctly

### GPU encoding not working

1. Check `VIDEO_GPU_CODEC` is supported on your platform
2. Verify GPU drivers are installed
3. Check worker logs for codec fallback messages
4. Test with `libx264` (CPU) as fallback

### WebSocket disconnects

1. Check CORS settings in `core/config.py`
2. Verify session ID is valid
3. Check nginx/proxy WebSocket upgrade headers
4. Frontend should implement reconnection logic

## Testing

```bash
# Run tests (if available)
uv run pytest

# Test ARQ worker directly
uv run arq core.arq_worker.WorkerSettings --check

# Test API endpoints
curl http://localhost:8000/docs
```

## Production Deployment

Recommendations:
1. Use Redis Sentinel or Redis Cluster for high availability
2. Scale ARQ workers horizontally
3. Monitor job queue lengths and worker CPU/memory
4. Set up health checks for workers
5. Use nginx for WebSocket load balancing
6. Configure log aggregation (ELK, CloudWatch, etc.)
7. Set up monitoring (Prometheus, Grafana)
