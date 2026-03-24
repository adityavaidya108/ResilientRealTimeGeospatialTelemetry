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
from backend.app.services.geospatial_service import add_or_update_location

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
                await add_or_update_location(
                    redis=websocket.app.state.redis,
                    key=settings.redis_drivers_geo_key,
                    member_id=message.device_id,
                    longitude=message.longitude,
                    latitude=message.latitude,
                )
                response = TelemetryAck(
                    device_id=message.device_id,
                    accepted=True,
                    sequence_no=message.sequence_no,
                )
                await websocket.send_json(server_message_to_json_dict(response))

            elif message.type == "bulk_sync":
                last_seq = None
                for item in message.items:
                    await add_or_update_location(
                        redis=websocket.app.state.redis,
                        key=settings.redis_drivers_geo_key,
                        member_id=message.device_id,
                        longitude=item.longitude,
                        latitude=item.latitude,
                    )
                    last_seq = item.sequence_no if item.sequence_no is not None else last_seq

                response = TelemetryAck(
                    device_id=message.device_id,
                    accepted=True,
                    sequence_no=last_seq,
                )
                await websocket.send_json(server_message_to_json_dict(response))

            elif message.type == "ride_request":
                await websocket.send_json(
                    {
                        "type": "ride_request_received",
                        "rider_id": message.rider_id,
                        "request_id": message.request_id,
                    }
                )

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
