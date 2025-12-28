import json
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import redis.asyncio as redis

from core.config import settings
from core.logging import get_logger

log = get_logger(__name__)


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(str, Enum):
    UPLOAD_PDF = "upload_pdf"
    GENERATE_PRESENTATION = "generate_presentation"
    GENERATE_VIDEO = "generate_video"


class JobManager:
    def __init__(self, redis_client: redis.Redis):
        self._redis = redis_client

    def _job_key(self, job_id: str) -> str:
        return f"job:{job_id}"

    def _job_result_key(self, job_id: str) -> str:
        return f"job:{job_id}:result"

    async def create_job(
        self, session_id: str, job_type: JobType, metadata: Optional[dict] = None
    ) -> tuple[str, Optional[str]]:
        from core.session import session_manager
        import uuid

        active_jobs = await session_manager.count_active_jobs(session_id)

        if active_jobs >= settings.max_concurrent_jobs_per_session:
            return (
                "",
                f"Rate limit exceeded. Max {settings.max_concurrent_jobs_per_session} concurrent jobs.",
            )

        job_id = str(uuid.uuid4())
        job_key = self._job_key(job_id)
        now = datetime.utcnow().isoformat()

        job_data = {
            "job_id": job_id,
            "session_id": session_id,
            "type": job_type.value,
            "status": JobStatus.PENDING.value,
            "progress": "0",
            "created_at": now,
            "updated_at": now,
            "error": "",
        }
        if metadata:
            job_data["metadata"] = str(metadata)

        await self._redis.hset(job_key, mapping=job_data)
        await self._redis.expire(job_key, settings.session_ttl_seconds)
        await session_manager.add_job_to_session(session_id, job_id)

        log.info(
            "job created", job_id=job_id, job_type=job_type.value, session_id=session_id
        )
        return job_id, None

    async def get_job(self, job_id: str) -> Optional[dict]:
        data = await self._redis.hgetall(self._job_key(job_id))
        if not data:
            return None
        if "progress" in data:
            data["progress"] = int(data["progress"])
        return data

    async def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        progress: Optional[int] = None,
        error: Optional[str] = None,
    ) -> bool:
        job_key = self._job_key(job_id)
        if not await self._redis.exists(job_key):
            return False

        updates = {"status": status.value, "updated_at": datetime.utcnow().isoformat()}
        if progress is not None:
            updates["progress"] = str(min(100, max(0, progress)))
        if error is not None:
            updates["error"] = error

        await self._redis.hset(job_key, mapping=updates)
        return True

    async def set_job_result(self, job_id: str, result: dict[str, Any]) -> bool:
        if not await self._redis.exists(self._job_key(job_id)):
            return False
        result_key = self._job_result_key(job_id)
        await self._redis.set(result_key, json.dumps(result))
        await self._redis.expire(result_key, settings.session_ttl_seconds)
        return True

    async def get_job_result(self, job_id: str) -> Optional[dict]:
        data = await self._redis.get(self._job_result_key(job_id))
        return json.loads(data) if data else None

    async def complete_job(self, job_id: str, result: Optional[dict] = None) -> bool:
        success = await self.update_job_status(
            job_id, JobStatus.COMPLETED, progress=100
        )
        if success and result:
            await self.set_job_result(job_id, result)
        return success

    async def fail_job(self, job_id: str, error: str) -> bool:
        return await self.update_job_status(job_id, JobStatus.FAILED, error=error)
