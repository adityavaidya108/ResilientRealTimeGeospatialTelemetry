"""FastAPI dependencies and shared resource helpers.

``main.py`` (lifespan) should:
    1. ``redis_client = await create_redis_client(settings)``
    2. ``app.state.redis = redis_client``
    3. On shutdown: ``await close_redis_client(redis_client)``

Route handlers and services can then use ``RedisDep`` / ``SettingsDep``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis

from backend.app.config import Settings, settings as default_settings


def get_settings() -> Settings:
    """Return application settings (singleton from env by default)."""
    return default_settings


async def create_redis_client(app_settings: Settings) -> Redis:
    """Create an async Redis client. Caller owns lifecycle (see ``close_redis_client``)."""
    return Redis.from_url(
        app_settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )


async def close_redis_client(client: Redis) -> None:
    """Close the async Redis connection pool."""
    await client.aclose()


async def get_redis(request: Request) -> Redis:
    """Inject Redis from ``request.app.state.redis`` (set during app lifespan)."""
    client = getattr(request.app.state, "redis", None)
    if client is None:
        raise RuntimeError(
            "Redis client missing on app.state; initialize it in the FastAPI lifespan handler."
        )
    return client


SettingsDep = Annotated[Settings, Depends(get_settings)]
RedisDep = Annotated[Redis, Depends(get_redis)]

__all__ = [
    "SettingsDep",
    "RedisDep",
    "close_redis_client",
    "create_redis_client",
    "get_redis",
    "get_settings",
]
