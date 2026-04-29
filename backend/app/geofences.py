from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CircleGeofence:
    """
    Circle geofence in WGS84.

    Center is stored as (lat, lon) for human readability.
    When querying Redis GEO, remember Redis expects (longitude, latitude).
    """

    geofence_id: str
    center_latitude: float
    center_longitude: float
    radius_m: float

