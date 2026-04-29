from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass(slots=True)
class QueuedPoint:
    latitude: float
    longitude: float
    timestamp_ms: int
    sequence_no: int


class TelemetryQueue:
    def __init__(self) -> None:
        self._items: deque[QueuedPoint] = deque()

    def enqueue(self, point: QueuedPoint) -> None:
        self._items.append(point)

    def drain_batch(self, max_items: int) -> list[QueuedPoint]:
        out: list[QueuedPoint] = []
        while self._items and len(out) < max_items:
            out.append(self._items.popleft())
        return out

    def __len__(self) -> int:
        return len(self._items)
