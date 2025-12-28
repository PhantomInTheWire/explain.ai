import logging

from fastapi import Request, Response, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from backend.core.session import session_manager

logger = logging.getLogger(__name__)

PUBLIC_PATHS = {
    "/",
    "/health",
    "/ready",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/sessions",
}
PUBLIC_PREFIXES = ("/docs", "/redoc")


class SessionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        if path in PUBLIC_PATHS or any(path.startswith(p) for p in PUBLIC_PREFIXES):
            return await call_next(request)

        if request.method == "OPTIONS":
            return await call_next(request)

        session_id = request.headers.get("X-Session-ID")
        if not session_id:
            raise HTTPException(status_code=401, detail="Missing X-Session-ID header")

        if not await session_manager.validate_session(session_id):
            raise HTTPException(status_code=401, detail="Invalid or expired session")

        await session_manager.refresh_session(session_id)
        request.state.session_id = session_id

        return await call_next(request)


def get_session_id(request: Request) -> str:
    session_id = getattr(request.state, "session_id", None)
    if not session_id:
        raise HTTPException(status_code=401, detail="Session not found")
    return session_id
