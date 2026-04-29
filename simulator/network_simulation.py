from __future__ import annotations

import random


class NetworkModel:
    """Simple probabilistic drop/reconnect state machine."""

    def __init__(self, *, drop_probability: float, seed: int) -> None:
        self._drop_probability = drop_probability
        self._rng = random.Random(seed)
        self._connected = True

    @property
    def connected(self) -> bool:
        return self._connected

    def should_drop_now(self) -> bool:
        if not self._connected:
            return False
        if self._rng.random() < self._drop_probability:
            self._connected = False
            return True
        return False

    def reconnect(self) -> None:
        self._connected = True
