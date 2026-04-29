from __future__ import annotations

import asyncio
import json
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from typing import Any

import websockets

from config import SimulatorConfig
from network_simulation import NetworkModel
from paths import CircularPath
from queueing import QueuedPoint, TelemetryQueue


@dataclass(slots=True)
class Metrics:
    sent_telemetry: int = 0
    queued: int = 0
    bulk_synced: int = 0
    drops: int = 0
    reconnects: int = 0
    acks: int = 0
    errors: int = 0


class SharedMetrics:
    def __init__(self, *, history_limit: int) -> None:
        self._totals = Metrics()
        self._history: deque[dict[str, int]] = deque(maxlen=history_limit)
        self._lock = threading.Lock()

    def add(self, **increments: int) -> None:
        with self._lock:
            for key, value in increments.items():
                setattr(self._totals, key, getattr(self._totals, key) + value)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return asdict(self._totals)

    def push_history_point(self) -> None:
        with self._lock:
            self._history.append(asdict(self._totals))

    def history(self) -> list[dict[str, int]]:
        with self._lock:
            return list(self._history)


class FleetSimulator:
    def __init__(self, config: SimulatorConfig) -> None:
        self.config = config.normalized()
        self.metrics = SharedMetrics(history_limit=self.config.history_limit)
        self._stop_event = asyncio.Event()

    def stop(self) -> None:
        self._stop_event.set()

    async def run(self) -> None:
        tasks = [
            asyncio.create_task(self._run_client(client_index=i))
            for i in range(self.config.fleet_size)
        ]
        history_task = asyncio.create_task(self._history_loop())
        try:
            await self._stop_event.wait()
        finally:
            for task in tasks:
                task.cancel()
            history_task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.gather(history_task, return_exceptions=True)

    async def _history_loop(self) -> None:
        while not self._stop_event.is_set():
            self.metrics.push_history_point()
            await asyncio.sleep(1.0)

    async def _run_client(self, client_index: int) -> None:
        device_id = f"sim-{client_index}"
        path = CircularPath(
            base_lat=self.config.base_lat,
            base_lon=self.config.base_lon,
            client_index=client_index,
        )
        network = NetworkModel(
            drop_probability=self.config.drop_probability,
            seed=client_index + 42,
        )
        queue = TelemetryQueue()
        sequence_no = 0

        websocket: Any | None = None
        while not self._stop_event.is_set():
            if websocket is None and network.connected:
                try:
                    websocket = await websockets.connect(self.config.ws_url)
                    self.metrics.add(reconnects=1)
                    await self._flush_queue(websocket, device_id, queue)
                except Exception:
                    self.metrics.add(errors=1)
                    websocket = None
                    network.reconnect()
                    await asyncio.sleep(self.config.reconnect_delay_seconds)
                    continue

            if network.should_drop_now():
                self.metrics.add(drops=1)
                if websocket is not None:
                    await websocket.close()
                    websocket = None

            lat, lon = path.next_point()
            point = QueuedPoint(
                latitude=lat,
                longitude=lon,
                timestamp_ms=int(time.time() * 1000),
                sequence_no=sequence_no,
            )
            sequence_no += 1

            if websocket is None:
                queue.enqueue(point)
                self.metrics.add(queued=1)
                await asyncio.sleep(self.config.reconnect_delay_seconds)
                network.reconnect()
                continue

            sent = await self._send_telemetry(websocket, device_id, point)
            if sent:
                self.metrics.add(sent_telemetry=1)
            else:
                queue.enqueue(point)
                self.metrics.add(queued=1, errors=1)
                await websocket.close()
                websocket = None
                await asyncio.sleep(self.config.reconnect_delay_seconds)
                network.reconnect()

            await asyncio.sleep(self.config.tick_seconds)

        if websocket is not None:
            await websocket.close()

    async def _send_telemetry(self, websocket: Any, device_id: str, point: QueuedPoint) -> bool:
        payload = {
            "type": "telemetry",
            "device_id": device_id,
            "latitude": point.latitude,
            "longitude": point.longitude,
            "timestamp_ms": point.timestamp_ms,
            "sequence_no": point.sequence_no,
        }
        try:
            await websocket.send(json.dumps(payload))
            return await self._consume_until_ack(websocket)
        except Exception:
            return False

    async def _flush_queue(
        self,
        websocket: Any,
        device_id: str,
        queue: TelemetryQueue,
    ) -> None:
        while len(queue) > 0 and not self._stop_event.is_set():
            batch = queue.drain_batch(self.config.bulk_sync_batch_size)
            items = [
                {
                    "latitude": p.latitude,
                    "longitude": p.longitude,
                    "timestamp_ms": p.timestamp_ms,
                    "sequence_no": p.sequence_no,
                }
                for p in batch
            ]
            payload = {"type": "bulk_sync", "device_id": device_id, "items": items}
            try:
                await websocket.send(json.dumps(payload))
                ok = await self._consume_until_ack(websocket)
                if ok:
                    self.metrics.add(bulk_synced=len(batch))
                    continue
            except Exception:
                pass

            for p in reversed(batch):
                queue.enqueue(p)
            return

    async def _consume_until_ack(self, websocket: Any) -> bool:
        deadline = asyncio.get_running_loop().time() + 3.0
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return False
            raw = await asyncio.wait_for(websocket.recv(), timeout=remaining)
            payload = json.loads(raw)
            msg_type = payload.get("type")
            if msg_type == "telemetry_ack":
                if payload.get("accepted"):
                    self.metrics.add(acks=1)
                    return True
                self.metrics.add(errors=1)
                return False


async def run_simulator(config: SimulatorConfig, simulator: FleetSimulator | None = None) -> FleetSimulator:
    sim = simulator or FleetSimulator(config)
    await sim.run()
    return sim
