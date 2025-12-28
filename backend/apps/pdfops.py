import asyncio
from pathlib import Path

import pdfplumber
from fastapi import HTTPException, UploadFile
from langchain.text_splitter import CharacterTextSplitter

from core.vectorstore import vectorstore_manager
from core.storage import storage_manager
from core.logging import get_logger

log = get_logger(__name__)


def extract_text_from_pdf_sync(file_path: Path) -> str:
    with pdfplumber.open(file_path) as pdf:
        text = ""
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text


async def extract_text_from_pdf(file_path: Path) -> str:
    return await asyncio.to_thread(extract_text_from_pdf_sync, file_path)


def process_file_context_sync(
    session_id: str, file_text: str, source_file: str = "uploaded.pdf"
) -> int:
    text_splitter = CharacterTextSplitter(
        separator="\n", chunk_size=1000, chunk_overlap=200, length_function=len
    )
    chunks = text_splitter.split_text(file_text)

    if not chunks:
        raise ValueError("No text chunks extracted from PDF")

    return vectorstore_manager.add_documents_sync(
        session_id=session_id, chunks=chunks, source_file=source_file
    )


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


def upload_file_sync(
    session_id: str, file_content: bytes, filename: str, content_type: str
) -> dict:
    if content_type != "application/pdf":
        raise ValueError("Invalid file format. Please upload a PDF file.")

    try:
        file_path = storage_manager.save_upload_sync(
            session_id=session_id, file_content=file_content, filename="source.pdf"
        )
        text = extract_text_from_pdf_sync(file_path)

        if not text.strip():
            raise ValueError("Could not extract text from PDF.")

        num_chunks = process_file_context_sync(
            session_id=session_id,
            file_text=text,
            source_file=filename,
        )

        return {
            "message": "PDF successfully processed.",
            "filename": filename,
            "chunks_created": num_chunks,
        }
    except Exception as e:
        log.error("upload failed", error=str(e))
        raise


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
        log.error("upload failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
