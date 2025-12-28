# ExplainAI

ExplainAI is an AI-driven platform that transforms PDF documents (e-books, research papers, reports) into professional PowerPoint presentations and narrated video lectures.

## Features
- **PDF-to-PPT:** Automatically extracts key insights and generates structured slides.
- **AI Narration:** Generates natural-sounding audio explanations for every slide.
- **Video Generation:** Produces a complete video lecture combining slides and audio.
- **RAG-Powered:** Uses Vector Search (Weaviate) to ensure high accuracy in content extraction.
- **Multi-User:** Session-based architecture with background job processing via Redis.

## Tech Stack
- **Frontend:** React, TypeScript, Tailwind CSS, Zustand, Vite.
- **Backend:** FastAPI (Python), asyncio, Redis, Weaviate, LangChain,
- **AI:** Google Gemini (LLM), Google Cloud Text-to-Speech.
- **Media:** MoviePy, python-pptx, pdfplumber, ConvertAPI.
- **Infrastructure:** Docker, Docker Compose.

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
   - `GOOGLE_API_KEY`
   - `CONVERTAPI_KEY`
   
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

## 🏗️ Architecture
The project follows a decoupled architecture:
- **`frontend/`**: React application using a wizard-like flow to guide users through the generation process.
- **`backend/`**: FastAPI server handling file processing, job orchestration with Redis, and AI integration.
- **`data/`**: (Volume) Persistent storage for session artifacts and vector database indices.
