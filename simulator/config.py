from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SimulatorConfig:
    ws_url: str = "ws://127.0.0.1:8000/ws"
    fleet_size: int = 100
    tick_seconds: float = 1.0
    drop_probability: float = 0.05
    reconnect_delay_seconds: float = 1.5
    bulk_sync_batch_size: int = 100
    base_lat: float = 38.8462
    base_lon: float = -77.3064
    history_limit: int = 300

    def normalized(self) -> "SimulatorConfig":
        return SimulatorConfig(
            ws_url=self.ws_url,
            fleet_size=max(1, int(self.fleet_size)),
            tick_seconds=max(0.1, float(self.tick_seconds)),
            drop_probability=min(1.0, max(0.0, float(self.drop_probability))),
            reconnect_delay_seconds=max(0.1, float(self.reconnect_delay_seconds)),
            bulk_sync_batch_size=max(1, int(self.bulk_sync_batch_size)),
            base_lat=min(90.0, max(-90.0, float(self.base_lat))),
            base_lon=min(180.0, max(-180.0, float(self.base_lon))),
            history_limit=max(10, int(self.history_limit)),
        )
