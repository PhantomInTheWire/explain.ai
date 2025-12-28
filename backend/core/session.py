import uuid
from datetime import datetime
from typing import Optional

import redis.asyncio as redis

from core.config import settings
from core.logging import get_logger

log = get_logger(__name__)


class SessionManager:
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self._redis: Optional[redis.Redis] = redis_client
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return
        if self._redis is None:
            self._redis = redis.from_url(
                settings.redis_url, encoding="utf-8", decode_responses=True
            )
        await self._redis.ping()
        self._initialized = True
        log.info("session manager initialized")

    async def close(self) -> None:
        if self._redis:
            await self._redis.close()
            self._initialized = False

    @property
    def redis(self) -> redis.Redis:
        if not self._initialized or self._redis is None:
            raise RuntimeError("Session manager not initialized")
        return self._redis

    def _session_key(self, session_id: str) -> str:
        return f"session:{session_id}"

    def _session_jobs_key(self, session_id: str) -> str:
        return f"session:{session_id}:jobs"

    async def create_session(self) -> str:
        session_id = str(uuid.uuid4())
        session_key = self._session_key(session_id)
        now = datetime.utcnow().isoformat()

        await self.redis.hset(
            session_key,
            mapping={"created_at": now, "last_access": now, "status": "active"},
        )
        await self.redis.expire(session_key, settings.session_ttl_seconds)
        log.info("session created", session_id=session_id)
        return session_id

    async def validate_session(self, session_id: str) -> bool:
        return bool(await self.redis.exists(self._session_key(session_id)))

    async def refresh_session(self, session_id: str) -> bool:
        session_key = self._session_key(session_id)
        if not await self.validate_session(session_id):
            return False

        await self.redis.hset(session_key, "last_access", datetime.utcnow().isoformat())
        await self.redis.expire(session_key, settings.session_ttl_seconds)

        jobs_key = self._session_jobs_key(session_id)
        if await self.redis.exists(jobs_key):
            await self.redis.expire(jobs_key, settings.session_ttl_seconds)
        return True

    async def get_session(self, session_id: str) -> Optional[dict]:
        session_key = self._session_key(session_id)
        data = await self.redis.hgetall(session_key)
        if not data:
            return None
        return {
            "session_id": session_id,
            **data,
            "ttl": await self.redis.ttl(session_key),
        }

    async def delete_session(self, session_id: str) -> bool:
        session_key = self._session_key(session_id)
        jobs_key = self._session_jobs_key(session_id)

        job_ids = await self.redis.lrange(jobs_key, 0, -1)
        if job_ids:
            job_keys = [f"job:{jid}" for jid in job_ids]
            job_result_keys = [f"job:{jid}:result" for jid in job_ids]
            await self.redis.delete(*job_keys, *job_result_keys)

        deleted = await self.redis.delete(session_key, jobs_key)
        if deleted:
            log.info("session deleted", session_id=session_id)
        return bool(deleted)

    async def list_sessions(self) -> list[str]:
        keys = []
        async for key in self.redis.scan_iter(match="session:*", count=100):
            if ":jobs" not in key:
                keys.append(key.replace("session:", ""))
        return keys

    async def add_job_to_session(self, session_id: str, job_id: str) -> None:
        jobs_key = self._session_jobs_key(session_id)
        await self.redis.rpush(jobs_key, job_id)
        await self.redis.expire(jobs_key, settings.session_ttl_seconds)

    async def get_session_jobs(self, session_id: str) -> list[str]:
        return await self.redis.lrange(self._session_jobs_key(session_id), 0, -1)

    async def count_active_jobs(self, session_id: str) -> int:
        job_ids = await self.get_session_jobs(session_id)
        count = 0
        for job_id in job_ids:
            status = await self.redis.hget(f"job:{job_id}", "status")
            if status in ("pending", "processing"):
                count += 1
        return count


session_manager = SessionManager()
