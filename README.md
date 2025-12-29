# ExplainAI

ExplainAI is an AI-driven platform that transforms PDF documents (e-books, research papers, reports) into professional PowerPoint presentations and narrated video lectures.

## Features
- **PDF-to-PPT:** Automatically extracts key insights and generates structured slides.
- **AI Narration:** Generates natural-sounding audio explanations for every slide.
- **Video Generation:** Produces a complete video lecture combining slides and audio with GPU acceleration support.
- **RAG-Powered:** Uses Vector Search (Weaviate) to ensure high accuracy in content extraction.
- **Real-Time Updates:** WebSocket support for live job progress tracking.
- **Multi-User:** Session-based architecture with async background job processing via ARQ.

## Tech Stack
- **Frontend:** React, TypeScript, Tailwind CSS, Zustand, Vite, WebSocket.
- **Backend:** FastAPI (Python), ARQ (async task queue), Redis, Weaviate, LangChain.
- **AI:** Google Gemini (LLM), Google Cloud Text-to-Speech.
- **Media:** MoviePy, python-pptx, pdfplumber, ConvertAPI.
- **Infrastructure:** Docker, Docker Compose, async/await throughout.

## 📦 Getting Started

### Prerequisites
- Docker and Docker Compose
- Google Cloud API Key (with Gemini and TTS enabled)
- ConvertAPI Key
- Google Cloud Service Account `credentials.json`

### Installation

1. **Environment Setup:**
   Copy `.env.example` to `.env` and fill in your API keys:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and provide:
   - `GOOGLE_API_KEY` - Your Google AI API key
   - `CONVERTAPI_KEY` - Your ConvertAPI key
   
   Optional ARQ worker configuration:
   - `ARQ_MAX_JOBS` - Max concurrent jobs for default worker (default: 10)
   - `ARQ_VIDEO_MAX_JOBS` - Max concurrent video jobs (default: 1)
   - `VIDEO_GPU_CODEC` - GPU codec for video encoding (default: h264_videotoolbox on macOS)
   
2. **Google Cloud Credentials:**
   Place your Google Cloud `credentials.json` in the root directory of the project.

3. **Run with Docker:**
   ```bash
   docker-compose up --build
   ```

4. **Access:**
   - **Frontend:** [http://localhost](http://localhost)
   - **API Backend:** [http://localhost:8000](http://localhost:8000)
   - **Interactive API Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
   - **WebSocket:** `ws://localhost:8000/api/ws/{session_id}`

## 🏗️ Architecture

The project follows a modern async architecture:

```
Frontend (React + WebSocket)
    ↓
FastAPI (async endpoints)
    ↓
ARQ Task Queue (Redis-based)
    ↓
Workers: Default (10 jobs) + Video (1 job, GPU-accelerated)
    ↓
External Services: Google AI, TTS, Weaviate, ConvertAPI
```

### Components

- **`frontend/`**: React application using a wizard-like flow with WebSocket for real-time updates.
- **`backend/`**: FastAPI server with ARQ for async job processing, WebSocket for real-time communication.
- **`data/`**: Persistent storage for session artifacts and vector database indices.

### Background Processing

The application uses ARQ (Async Redis Queue) with two specialized workers:

1. **Default Worker**: Handles PDF processing, prompt generation, PPT creation (10 concurrent jobs)
2. **Video Worker**: Handles video encoding with GPU acceleration (1 concurrent job by default)

### GPU Acceleration

Video encoding supports GPU acceleration on multiple platforms:
- **macOS:** `h264_videotoolbox` (Apple VideoToolbox - default)
- **NVIDIA:** `h264_nvenc` (NVIDIA NVENC)
- **Intel:** `h264_qsv` (Intel Quick Sync Video)
- **CPU:** `libx264` (software encoding - fallback)

Configure via `VIDEO_GPU_CODEC` environment variable.

## 🔧 Configuration

Key environment variables:

```bash
# Required API Keys
GOOGLE_API_KEY=your-google-api-key-here
CONVERTAPI_KEY=your-convertapi-key-here
GOOGLE_APPLICATION_CREDENTIALS=/app/credentials.json

# Redis & Weaviate
REDIS_URL=redis://redis:6379
WEAVIATE_URL=http://weaviate:8080

# ARQ Worker Configuration
ARQ_MAX_JOBS=10              # Default worker concurrency
ARQ_VIDEO_MAX_JOBS=1         # Video worker concurrency
VIDEO_GPU_CODEC=h264_videotoolbox  # GPU codec selection

# Session Management
SESSION_TTL_SECONDS=3600
DATA_DIR=/data/sessions
CLEANUP_INTERVAL_SECONDS=300

# CORS
CORS_ORIGINS=http://localhost,http://localhost:80
```

See `.env.example` for complete configuration options.

## 🚀 Development

### Running Locally (without Docker)

**Backend:**
```bash
cd backend
uv sync
uv run uvicorn main:app --reload
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

**ARQ Workers:**
```bash
cd backend
uv run arq core.arq_worker.WorkerSettings  # Default worker
uv run arq core.arq_worker.VideoWorkerSettings  # Video worker
```

### WebSocket Usage

Connect to `ws://localhost:8000/api/ws/{session_id}` to receive real-time job progress:

```javascript
const ws = new WebSocket(`ws://localhost:8000/api/ws/${sessionId}`);
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Job progress:', data);
};
```

## 📝 Project Structure

```
vedanta/
├── backend/
│   ├── apps/              # Application logic (PDF, PPT, audio, video)
│   ├── core/              # Core utilities (ARQ, WebSocket, storage)
│   ├── theme_pptx/        # PowerPoint themes
│   └── main.py            # FastAPI application
├── frontend/
│   ├── src/
│   │   ├── components/    # React components
│   │   ├── store/         # Zustand state management
│   │   └── api/           # API client + WebSocket
│   └── vite.config.ts
├── docker-compose.yml     # Multi-container setup
└── .env.example           # Configuration template
```
