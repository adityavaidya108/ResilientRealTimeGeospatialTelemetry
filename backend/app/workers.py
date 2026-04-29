from __future__ import annotations

import asyncio
import contextlib
import logging
import time

from redis.asyncio import Redis

from backend.app.config import Settings
from backend.app.connection_manager import ConnectionManager
from backend.app.models import GeofenceEnteredMessage, server_message_to_json_dict
from backend.app.services.geospatial_service import list_members_within_radius

logger = logging.getLogger(__name__)


async def run_geofence_entry_worker(
    *,
    redis: Redis,
    settings: Settings,
    connection_manager: ConnectionManager,
) -> None:
    """Continuously detect geofence entries and push alerts to active sockets."""
    previous_by_geofence: dict[str, set[str]] = {}

    while True:
        try:
            for geofence in settings.geofences:
                members = await list_members_within_radius(
                    redis=redis,
                    key=settings.redis_drivers_geo_key,
                    center_longitude=geofence.center_longitude,
                    center_latitude=geofence.center_latitude,
                    radius_m=geofence.radius_m,
                )

                current_ids = {member.member_id for member in members}
                previous_ids = previous_by_geofence.get(geofence.geofence_id, set())
                newly_entered_ids = current_ids - previous_ids

                if newly_entered_ids:
                    now_unix = time.time()
                    for device_id in newly_entered_ids:
                        websocket = await connection_manager.get(device_id)
                        if websocket is None:
                            continue
                        payload = GeofenceEnteredMessage(
                            device_id=device_id,
                            geofence_id=geofence.geofence_id,
                            entered_at_unix=now_unix,
                        )
                        with contextlib.suppress(Exception):
                            await websocket.send_json(server_message_to_json_dict(payload))

                previous_by_geofence[geofence.geofence_id] = current_ids

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Geofence entry worker iteration failed")

        await asyncio.sleep(settings.worker_poll_interval_seconds)
