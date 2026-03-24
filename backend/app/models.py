"""Pydantic models for WebSocket JSON payloads.

Client → server messages use a discriminated union on the ``type`` field.
Server → client messages are plain models you serialize with ``model_dump(mode="json")``.

Requires: pydantic v2 (pulled in by FastAPI).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

# ---------------------------------------------------------------------------
# Client → server
# ---------------------------------------------------------------------------


class TelemetryMessage(BaseModel):
    """Single location update from a device (driver or rider)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["telemetry"] = "telemetry"
    device_id: str = Field(..., min_length=1, max_length=256)
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    timestamp_ms: int | None = Field(
        default=None,
        description="Client-reported time in milliseconds since epoch.",
    )
    sequence_no: int | None = Field(
        default=None,
        ge=0,
        description="Monotonic per-device sequence for dedup / bulk replay.",
    )


class RideRequestMessage(BaseModel):
    """Rider asks for a cab: random driver pick inside radius."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["ride_request"] = "ride_request"
    rider_id: str = Field(..., min_length=1, max_length=256)
    center_latitude: float = Field(..., ge=-90.0, le=90.0)
    center_longitude: float = Field(..., ge=-180.0, le=180.0)
    radius_m: float = Field(..., gt=0, le=50_000, description="Pickup radius in meters.")
    request_id: str | None = Field(
        default=None,
        max_length=256,
        description="Optional idempotency / tracing id from client.",
    )


class BulkTelemetryItem(BaseModel):
    """One point inside a bulk_sync batch."""

    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    timestamp_ms: int | None = None
    sequence_no: int | None = Field(default=None, ge=0)


class BulkSyncMessage(BaseModel):
    """Replay buffered telemetry after reconnect (simulator / mobile)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["bulk_sync"] = "bulk_sync"
    device_id: str = Field(..., min_length=1, max_length=256)
    items: list[BulkTelemetryItem] = Field(
        ...,
        min_length=1,
        max_length=10_000,
        description="Ordered batch of points to apply.",
    )


ClientMessage = Annotated[
    Union[TelemetryMessage, RideRequestMessage, BulkSyncMessage],
    Field(discriminator="type"),
]

_client_message_adapter: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)


def parse_client_message(data: Any) -> TelemetryMessage | RideRequestMessage | BulkSyncMessage:
    """Parse and validate a client JSON object (dict) into a typed message."""
    return _client_message_adapter.validate_python(data)


# ---------------------------------------------------------------------------
# Server → client
# ---------------------------------------------------------------------------


class TelemetryAck(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["telemetry_ack"] = "telemetry_ack"
    device_id: str
    accepted: bool
    sequence_no: int | None = None
    error_code: str | None = None


class AssignedDriverMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["assigned_driver"] = "assigned_driver"
    rider_id: str
    assigned_driver_id: str
    request_id: str | None = None


class NoDriverAvailableMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["no_driver_available"] = "no_driver_available"
    rider_id: str
    request_id: str | None = None


class DriverLocationUpdateMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["driver_location_update"] = "driver_location_update"
    rider_id: str
    driver_id: str
    latitude: float
    longitude: float
    forwarded_at_unix: float = Field(
        ...,
        description="Server time when this update was forwarded (Unix seconds, float).",
    )


class AssignmentExpiredMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["assignment_expired"] = "assignment_expired"
    rider_id: str


ServerMessage = (
    TelemetryAck
    | AssignedDriverMessage
    | NoDriverAvailableMessage
    | DriverLocationUpdateMessage
    | AssignmentExpiredMessage
)


def server_message_to_json_dict(msg: ServerMessage) -> dict[str, Any]:
    """Serialize an outbound server message for WebSocket JSON text."""
    return msg.model_dump(mode="json")
