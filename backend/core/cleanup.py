import asyncio
import logging
from typing import Optional

from backend.core.config import settings
from backend.core.session import session_manager
from backend.core.vectorstore import vectorstore_manager
from backend.core.storage import storage_manager

logger = logging.getLogger(__name__)


class CleanupTask:
    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            f"Cleanup task started (interval: {settings.cleanup_interval_seconds}s)"
        )

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Cleanup task stopped")

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await self._cleanup()
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
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
            logger.info(f"Cleaned {cleaned} expired sessions")

    async def _cleanup_session(self, session_id: str) -> None:
        try:
            await vectorstore_manager.delete_session_collection(session_id)
        except Exception as e:
            logger.warning(f"Error deleting Weaviate collection for {session_id}: {e}")

        try:
            storage_manager.delete_session_directory(session_id)
        except Exception as e:
            logger.warning(f"Error deleting storage for {session_id}: {e}")

        try:
            await session_manager.delete_session(session_id)
        except Exception as e:
            logger.warning(f"Error deleting Redis keys for {session_id}: {e}")


cleanup_task = CleanupTask()
