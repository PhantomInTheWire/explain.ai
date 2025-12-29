import asyncio
from typing import Optional
from collections import defaultdict

from fastapi import WebSocket
from core.logging import get_logger

log = get_logger(__name__)


class WebSocketManager:
    def __init__(self):
        self.connections: dict[str, list[WebSocket]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self.connections[session_id].append(websocket)
        log.debug(
            "websocket connected",
            session_id=session_id,
            total=len(self.connections[session_id]),
        )

    async def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            if session_id in self.connections:
                try:
                    self.connections[session_id].remove(websocket)
                    if not self.connections[session_id]:
                        del self.connections[session_id]
                except ValueError:
                    pass
        log.debug("websocket disconnected", session_id=session_id)

    async def broadcast(self, session_id: str, message: dict) -> None:
        async with self._lock:
            connections = self.connections.get(session_id, []).copy()

        if not connections:
            log.debug("no websocket connections for broadcast", session_id=session_id)
            return

        dead_connections = []
        for websocket in connections:
            try:
                await websocket.send_json(message)
            except Exception as e:
                log.warning(
                    "failed to send websocket message",
                    session_id=session_id,
                    error=str(e),
                )
                dead_connections.append(websocket)

        if dead_connections:
            async with self._lock:
                for ws in dead_connections:
                    try:
                        self.connections[session_id].remove(ws)
                    except (ValueError, KeyError):
                        pass
                if session_id in self.connections and not self.connections[session_id]:
                    del self.connections[session_id]

        log.debug(
            "websocket broadcast sent",
            session_id=session_id,
            recipients=len(connections) - len(dead_connections),
            message_type=message.get("type"),
        )

    async def broadcast_job_update(
        self,
        session_id: str,
        job_id: str,
        status: str,
        progress: int,
        error: str = "",
        result: Optional[dict] = None,
    ) -> None:
        message = {
            "type": "job_update",
            "job_id": job_id,
            "status": status,
            "progress": progress,
        }
        if error:
            message["error"] = error
        if result:
            message["result"] = result

        await self.broadcast(session_id, message)


websocket_manager = WebSocketManager()
