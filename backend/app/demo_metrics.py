from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from dataclasses import dataclass

from backend.app.connection_manager import ConnectionManager

# Use Uvicorn's error logger so metrics are always visible in console output.
logger = logging.getLogger("uvicorn.error")


@dataclass(slots=True)
class MetricsSnapshot:
    telemetry_messages: int = 0
    bulk_sync_messages: int = 0
    bulk_sync_items: int = 0
    geofence_checks: int = 0
    geofence_entries_detected: int = 0
    geofence_alerts_sent: int = 0
    websocket_disconnects: int = 0


class DemoMetrics:
    """Tiny async-safe counters for console demonstration logging."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._snapshot = MetricsSnapshot()

    async def inc(self, field: str, value: int = 1) -> None:
        async with self._lock:
            setattr(self._snapshot, field, getattr(self._snapshot, field) + value)

    async def get_snapshot(self) -> MetricsSnapshot:
        async with self._lock:
            return MetricsSnapshot(**asdict(self._snapshot))


async def run_demo_metrics_logger(
    *,
    metrics: DemoMetrics,
    connection_manager: ConnectionManager,
    interval_seconds: float,
) -> None:
    logger.info("demo_metrics logger started interval_seconds=%s", interval_seconds)
    while True:
        snapshot = await metrics.get_snapshot()
        active_connections = await connection_manager.count()
        logger.info(
            "demo_metrics active_connections=%s telemetry_messages=%s bulk_sync_messages=%s "
            "bulk_sync_items=%s geofence_checks=%s geofence_entries_detected=%s "
            "geofence_alerts_sent=%s websocket_disconnects=%s",
            active_connections,
            snapshot.telemetry_messages,
            snapshot.bulk_sync_messages,
            snapshot.bulk_sync_items,
            snapshot.geofence_checks,
            snapshot.geofence_entries_detected,
            snapshot.geofence_alerts_sent,
            snapshot.websocket_disconnects,
        )
        await asyncio.sleep(interval_seconds)
