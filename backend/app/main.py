from __future__ import annotations

import json
import logging
import asyncio
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from backend.app.config import settings
from backend.app.connection_manager import ConnectionManager
from backend.app.demo_metrics import DemoMetrics, run_demo_metrics_logger
from backend.app.dependencies import close_redis_client, create_redis_client
from backend.app.models import TelemetryAck, parse_client_message, server_message_to_json_dict
from backend.app.services.telemetry_service import (
    handle_bulk_sync,
    handle_ride_request,
    handle_telemetry,
)
from backend.app.workers import run_geofence_entry_worker

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    redis_client = await create_redis_client(settings)
    connection_manager = ConnectionManager()
    demo_metrics = DemoMetrics()
    geofence_worker_task = asyncio.create_task(
        run_geofence_entry_worker(
            redis=redis_client,
            settings=settings,
            connection_manager=connection_manager,
            metrics=demo_metrics,
        )
    )
    demo_metrics_logger_task = asyncio.create_task(
        run_demo_metrics_logger(
            metrics=demo_metrics,
            connection_manager=connection_manager,
            interval_seconds=settings.demo_metrics_log_interval_seconds,
        )
    )
    app.state.redis = redis_client
    app.state.connection_manager = connection_manager
    app.state.demo_metrics = demo_metrics
    app.state.geofence_worker_task = geofence_worker_task
    app.state.demo_metrics_logger_task = demo_metrics_logger_task
    try:
        yield
    finally:
        geofence_worker_task.cancel()
        demo_metrics_logger_task.cancel()
        for task in (geofence_worker_task, demo_metrics_logger_task):
            try:
                await task
            except asyncio.CancelledError:
                pass
        await close_redis_client(redis_client)


app = FastAPI(title="Resilient Real-Time Geospatial Telemetry", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.websocket("/ws")
# This function expects a parameter named websocket, and it should be of type WebSocket
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    redis_client = websocket.app.state.redis
    connection_manager = websocket.app.state.connection_manager
    demo_metrics = websocket.app.state.demo_metrics

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
                await connection_manager.register(message.device_id, websocket)
                await demo_metrics.inc("telemetry_messages")
                response = await handle_telemetry(
                    redis=redis_client,
                    settings=settings,
                    message=message,
                )
            elif message.type == "bulk_sync":
                await demo_metrics.inc("bulk_sync_messages")
                await demo_metrics.inc("bulk_sync_items", len(message.items))
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
        await connection_manager.remove_websocket(websocket)
        await demo_metrics.inc("websocket_disconnects")
        logger.info("WebSocket disconnected")
