from __future__ import annotations

import math


class CircularPath:
    """Very small circular motion around a base coordinate."""

    def __init__(self, *, base_lat: float, base_lon: float, client_index: int) -> None:
        self._base_lat = base_lat
        self._base_lon = base_lon
        self._phase = (client_index % 360) * (math.pi / 180.0)
        self._step = 0
        self._radius_lat = 0.003 + ((client_index % 7) * 0.0002)
        self._radius_lon = 0.003 + ((client_index % 5) * 0.0002)

    def next_point(self) -> tuple[float, float]:
        angle = self._phase + self._step * 0.07
        self._step += 1
        lat = self._base_lat + self._radius_lat * math.sin(angle)
        lon = self._base_lon + self._radius_lon * math.cos(angle)
        return lat, lon
