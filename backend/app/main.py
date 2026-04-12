from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from backend.app.config import settings
from backend.app.dependencies import close_redis_client, create_redis_client
from backend.app.models import TelemetryAck, parse_client_message, server_message_to_json_dict
from backend.app.services.telemetry_service import (
    handle_bulk_sync,
    handle_ride_request,
    handle_telemetry,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    redis_client = await create_redis_client(settings)
    app.state.redis = redis_client
    try:
        yield
    finally:
        await close_redis_client(redis_client)


app = FastAPI(title="Resilient Real-Time Geospatial Telemetry", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    redis_client = websocket.app.state.redis

    try:
        while True:
            raw_text = await websocket.receive_text()

            try:
                payload: Any = json.loads(raw_text)
            except json.JSONDecodeError:
                await websocket.send_json(
                    server_message_to_json_dict(
                        TelemetryAck(
                            device_id="unknown",
                            accepted=False,
                            error_code="invalid_json",
                        )
                    )
                )
                continue

            try:
                message = parse_client_message(payload)
            except ValidationError:
                await websocket.send_json(
                    server_message_to_json_dict(
                        TelemetryAck(
                            device_id=payload.get("device_id", "unknown")
                            if isinstance(payload, dict)
                            else "unknown",
                            accepted=False,
                            error_code="validation_error",
                        )
                    )
                )
                continue

            if message.type == "telemetry":
                response = await handle_telemetry(
                    redis=redis_client,
                    settings=settings,
                    message=message,
                )
            elif message.type == "bulk_sync":
                response = await handle_bulk_sync(
                    redis=redis_client,
                    settings=settings,
                    message=message,
                )
            else:
                response = await handle_ride_request(
                    redis=redis_client,
                    settings=settings,
                    message=message,
                )

            await websocket.send_json(server_message_to_json_dict(response))

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
