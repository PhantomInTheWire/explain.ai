import logging
from pathlib import Path

import pdfplumber
from fastapi import HTTPException, UploadFile
from langchain.text_splitter import CharacterTextSplitter

from backend.core.vectorstore import vectorstore_manager
from backend.core.storage import storage_manager

logger = logging.getLogger(__name__)


async def extract_text_from_pdf(file_path: Path) -> str:
    with pdfplumber.open(file_path) as pdf:
        text = ""
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text


async def process_file_context(
    session_id: str, file_text: str, source_file: str = "uploaded.pdf"
) -> int:
    text_splitter = CharacterTextSplitter(
        separator="\n", chunk_size=1000, chunk_overlap=200, length_function=len
    )
    chunks = text_splitter.split_text(file_text)

    if not chunks:
        raise ValueError("No text chunks extracted from PDF")

    return await vectorstore_manager.add_documents(
        session_id=session_id, chunks=chunks, source_file=source_file
    )


async def upload_file(session_id: str, file: UploadFile) -> dict:
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=400, detail="Invalid file format. Please upload a PDF file."
        )

    try:
        file_content = await file.read()
        file_path = await storage_manager.save_upload(
            session_id=session_id, file_content=file_content, filename="source.pdf"
        )
        text = await extract_text_from_pdf(file_path)

        if not text.strip():
            raise HTTPException(
                status_code=400, detail="Could not extract text from PDF."
            )

        num_chunks = await process_file_context(
            session_id=session_id,
            file_text=text,
            source_file=file.filename or "uploaded.pdf",
        )

        return {
            "message": "PDF successfully processed.",
            "filename": file.filename,
            "chunks_created": num_chunks,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading file: {e}")
        raise HTTPException(status_code=500, detail=str(e))
