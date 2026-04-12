"""Async Redis GEO helpers.

Redis ``GEOADD`` expects **longitude, latitude** (X, Y) order — not lat/lon.

Callers pass the sorted-set **key** explicitly (e.g. ``settings.redis_drivers_geo_key``)
so the same functions can index drivers, riders, or other device sets without coupling
this module to ``config.Settings``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from redis.asyncio import Redis

__all__ = [
    "GeoPoint",
    "MemberInRadius",
    "add_or_update_location",
    "add_or_update_locations_batch",
    "get_location",
    "list_members_within_radius",
    "remove_member",
]


@dataclass(frozen=True, slots=True)
class GeoPoint:
    """A WGS84 point."""

    longitude: float
    latitude: float


@dataclass(frozen=True, slots=True)
class MemberInRadius:
    """One member returned from a radius search."""

    member_id: str
    distance_m: float
    point: GeoPoint


async def add_or_update_location(
    redis: Redis,
    key: str,
    member_id: str,
    longitude: float,
    latitude: float,
) -> int:
    """GEOADD one member. Returns count of new elements added (0 if updated only)."""
    # redis-py expects a flat sequence: lon, lat, member, ...
    n = await redis.geoadd(key, [longitude, latitude, member_id])
    return int(n) if n is not None else 0


async def add_or_update_locations_batch(
    redis: Redis,
    key: str,
    items: Sequence[tuple[str, float, float]],
) -> int:
    """
    GEOADD many members.

    ``items`` is ``(member_id, longitude, latitude)`` per row.
    Returns number of new elements added (per Redis GEOADD CH semantics may vary by server).
    """
    if not items:
        return 0
    values: list[tuple[float, float, str]] = [
        (lon, lat, member_id) for member_id, lon, lat in items
    ]
    n = await redis.geoadd(key, values)
    return int(n) if n is not None else 0


async def get_location(redis: Redis, key: str, member_id: str) -> GeoPoint | None:
    """GEOPOS for a single member; returns ``None`` if missing."""
    raw: Any = await redis.geopos(key, member_id)
    if not raw or raw[0] is None:
        return None
    pair = raw[0]
    # redis-py returns (lon, lat) as strings or floats depending on version / decode
    lon_s, lat_s = pair[0], pair[1]
    return GeoPoint(longitude=float(lon_s), latitude=float(lat_s))


async def list_members_within_radius(
    redis: Redis,
    key: str,
    center_longitude: float,
    center_latitude: float,
    radius_m: float,
    *,
    count: int | None = None,
) -> list[MemberInRadius]:
    """
    GEOSEARCH (BYRADIUS) around a center point.

    ``count`` maps to Redis ``COUNT`` (optional cap). For random driver selection,
    callers can omit ``count`` and choose randomly in application logic.
    """
    kwargs: dict[str, Any] = {
        "longitude": center_longitude,
        "latitude": center_latitude,
        "radius": radius_m,
        "unit": "m",
        "withdist": True,
        "withcoord": True,
    }
    if count is not None:
        kwargs["count"] = count

    rows: Any = await redis.geosearch(key, **kwargs)

    out: list[MemberInRadius] = []
    for row in rows or []:
        parsed = _parse_geosearch_row(row)
        if parsed is not None:
            out.append(parsed)
    return out


def _parse_geosearch_row(row: Any) -> MemberInRadius | None:
    """Normalize redis-py geosearch row shapes."""
    if row is None:
        return None

    # Common shape: (member, distance, (lon, lat))
    if isinstance(row, (list, tuple)) and len(row) >= 3:
        member_id, dist, coord = row[0], row[1], row[2]
        if not isinstance(member_id, str):
            member_id = str(member_id)
        if coord is None or not isinstance(coord, (list, tuple)) or len(coord) < 2:
            return None
        lon, lat = coord[0], coord[1]
        return MemberInRadius(
            member_id=member_id,
            distance_m=float(dist),
            point=GeoPoint(longitude=float(lon), latitude=float(lat)),
        )

    # Fallback: member only
    if isinstance(row, (list, tuple)) and len(row) == 1:
        return None

    if isinstance(row, str):
        return None

    return None


async def remove_member(redis: Redis, key: str, member_id: str) -> int:
    """Remove a member from the GEO key (underlying ZSET). Returns ZREM count."""
    return int(await redis.zrem(key, member_id))
