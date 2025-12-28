import asyncio
from typing import Optional

from backend.core.config import settings
from backend.core.session import session_manager
from backend.core.vectorstore import vectorstore_manager
from backend.core.storage import storage_manager
from backend.core.logging import get_logger

log = get_logger(__name__)


class CleanupTask:
    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        log.info("cleanup task started", interval=settings.cleanup_interval_seconds)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("cleanup task stopped")

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await self._cleanup()
            except Exception as e:
                log.error("cleanup error", error=str(e))
            await asyncio.sleep(settings.cleanup_interval_seconds)

    async def _cleanup(self) -> None:
        redis_sessions = set(await session_manager.list_sessions())
        storage_sessions = set(storage_manager.list_sessions())
        weaviate_sessions = set(await vectorstore_manager.list_collections())
        all_sessions = redis_sessions | storage_sessions | weaviate_sessions

        cleaned = 0
        for session_id in all_sessions:
            if not await session_manager.validate_session(session_id):
                await self._cleanup_session(session_id)
                cleaned += 1

        if cleaned:
            log.info("expired sessions cleaned", count=cleaned)

    async def _cleanup_session(self, session_id: str) -> None:
        try:
            await vectorstore_manager.delete_session_collection(session_id)
        except Exception as e:
            log.warning(
                "failed to delete weaviate collection",
                session_id=session_id,
                error=str(e),
            )

        try:
            await storage_manager.delete_session_directory_async(session_id)
        except Exception as e:
            log.warning("failed to delete storage", session_id=session_id, error=str(e))

        try:
            await session_manager.delete_session(session_id)
        except Exception as e:
            log.warning(
                "failed to delete redis keys", session_id=session_id, error=str(e)
            )


cleanup_task = CleanupTask()
