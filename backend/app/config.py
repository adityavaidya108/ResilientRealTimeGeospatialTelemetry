"""Application configuration loaded from environment variables.

No FastAPI imports here — this module is the foundation for dependencies and services.

Environment variables (all optional unless noted):
    REDIS_URL
        Redis connection URL (default: redis://localhost:6379/0).
    REDIS_DRIVERS_GEO_KEY
        Redis GEO sorted set name for driver positions (default: drivers:geo).
    ASSIGNMENT_TTL_SECONDS
        How long a rider–driver assignment stays valid (default: 900 = 15 minutes).
    FORWARD_INTERVAL_SECONDS_TIER_A / FORWARD_DISTANCE_MILES_TIER_A
        Forward driver location to rider if at least this many seconds (server time)
        since last forward AND driver moved at least this many miles since last forward
        (defaults: 600 s, 2.0 mi).
    FORWARD_INTERVAL_SECONDS_TIER_B / FORWARD_DISTANCE_MILES_TIER_B
        Second, more frequent tier (defaults: 300 s, 1.0 mi).
    WORKER_POLL_INTERVAL_SECONDS
        Sleep between background worker iterations (default: 1.0).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from backend.app.geofences import CircleGeofence


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw, 10)


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


@dataclass(frozen=True, slots=True)
class Settings:
    """Immutable settings snapshot."""

    redis_url: str
    redis_drivers_geo_key: str
    assignment_ttl_seconds: int
    forward_interval_seconds_tier_a: int
    forward_distance_miles_tier_a: float
    forward_interval_seconds_tier_b: int
    forward_distance_miles_tier_b: float
    worker_poll_interval_seconds: float
    log_level: str
    geofences: tuple[CircleGeofence, ...]

    @classmethod
    def from_env(cls) -> Settings:
        # Default/demo geofence: Fairfax, VA (approx center). Override via env for experiments.
        fairfax_center_lat = _get_float("FAIRFAX_CENTER_LAT", 38.8462)
        fairfax_center_lon = _get_float("FAIRFAX_CENTER_LON", -77.3064)
        fairfax_radius_m = _get_float("FAIRFAX_RADIUS_M", 5_000.0)

        return cls(
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            redis_drivers_geo_key=os.getenv("REDIS_DRIVERS_GEO_KEY", "drivers:geo"),
            assignment_ttl_seconds=_get_int("ASSIGNMENT_TTL_SECONDS", 900),
            forward_interval_seconds_tier_a=_get_int(
                "FORWARD_INTERVAL_SECONDS_TIER_A", 600
            ),
            forward_distance_miles_tier_a=_get_float(
                "FORWARD_DISTANCE_MILES_TIER_A", 2.0
            ),
            forward_interval_seconds_tier_b=_get_int(
                "FORWARD_INTERVAL_SECONDS_TIER_B", 300
            ),
            forward_distance_miles_tier_b=_get_float(
                "FORWARD_DISTANCE_MILES_TIER_B", 1.0
            ),
            worker_poll_interval_seconds=_get_float(
                "WORKER_POLL_INTERVAL_SECONDS", 1.0
            ),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            geofences=(
                CircleGeofence(
                    geofence_id="fairfax_demo",
                    center_latitude=fairfax_center_lat,
                    center_longitude=fairfax_center_lon,
                    radius_m=fairfax_radius_m,
                ),
            ),
        )


# Default instance for app wiring; tests can replace via monkeypatch or explicit injection.
settings = Settings.from_env()

__all__ = ["Settings", "settings"]
