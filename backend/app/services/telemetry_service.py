"""Telemetry service layer.

This module holds the "business logic" for handling validated client messages:
- persist telemetry into Redis GEO indices
- select drivers for ride requests using Redis GEOSEARCH BYRADIUS

`backend/app/main.py` should stay thin: websocket transport + parsing + calling
these functions, then sending the returned server message.
"""

from __future__ import annotations

import random
from typing import Iterable

from redis.asyncio import Redis

from backend.app.config import Settings
from backend.app.models import (
    AssignedDriverMessage,
    BulkSyncMessage,
    NoDriverAvailableMessage,
    RideRequestMessage,
    ServerMessage,
    TelemetryAck,
    TelemetryMessage,
)
from backend.app.services.geospatial_service import (
    add_or_update_location,
    list_members_within_radius,
)

__all__ = [
    "handle_bulk_sync",
    "handle_ride_request",
    "handle_telemetry",
]


async def handle_telemetry(
    *,
    redis: Redis,
    settings: Settings,
    message: TelemetryMessage,
) -> TelemetryAck:
    """Persist one point and return an ACK."""
    await add_or_update_location(
        redis=redis,
        key=settings.redis_drivers_geo_key,
        member_id=message.device_id,
        longitude=message.longitude,
        latitude=message.latitude,
    )
    return TelemetryAck(
        device_id=message.device_id,
        accepted=True,
        sequence_no=message.sequence_no,
    )


async def handle_bulk_sync(
    *,
    redis: Redis,
    settings: Settings,
    message: BulkSyncMessage,
) -> TelemetryAck:
    """Apply a batch of points; Redis GEO keeps the last point for the member."""
    last_seq: int | None = None
    for item in message.items:
        await add_or_update_location(
            redis=redis,
            key=settings.redis_drivers_geo_key,
            member_id=message.device_id,
            longitude=item.longitude,
            latitude=item.latitude,
        )
        if item.sequence_no is not None:
            last_seq = item.sequence_no

    return TelemetryAck(
        device_id=message.device_id,
        accepted=True,
        sequence_no=last_seq,
    )


def _pick_random_member_ids(member_ids: Iterable[str]) -> str | None:
    ids = list(member_ids)
    if not ids:
        return None
    return random.choice(ids)


async def handle_ride_request(
    *,
    redis: Redis,
    settings: Settings,
    message: RideRequestMessage,
) -> ServerMessage:
    """Pick a random driver within radius and return assignment / no-driver."""
    candidates = await list_members_within_radius(
        redis=redis,
        key=settings.redis_drivers_geo_key,
        center_longitude=message.center_longitude,
        center_latitude=message.center_latitude,
        radius_m=message.radius_m,
    )
    picked = _pick_random_member_ids([c.member_id for c in candidates])
    if picked is None:
        return NoDriverAvailableMessage(rider_id=message.rider_id, request_id=message.request_id)

    return AssignedDriverMessage(
        rider_id=message.rider_id,
        assigned_driver_id=picked,
        request_id=message.request_id,
    )

