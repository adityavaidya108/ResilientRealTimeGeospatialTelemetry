from __future__ import annotations

import asyncio

from fastapi import WebSocket


class ConnectionManager:
    """Thread-safe mapping of device_id to active websocket."""

    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()

    async def register(self, device_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections[device_id] = websocket

    async def get(self, device_id: str) -> WebSocket | None:
        async with self._lock:
            return self._connections.get(device_id)

    async def remove_device(self, device_id: str) -> None:
        async with self._lock:
            self._connections.pop(device_id, None)

    async def remove_websocket(self, websocket: WebSocket) -> None:
        async with self._lock:
            stale_ids = [
                device_id
                for device_id, active_websocket in self._connections.items()
                if active_websocket is websocket
            ]
            for device_id in stale_ids:
                self._connections.pop(device_id, None)
