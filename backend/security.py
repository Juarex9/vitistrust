"""CORS helpers, rate limiting, and admin API key authentication."""

import logging
import os
import time
from collections import defaultdict
from threading import Lock

from fastapi import Header, HTTPException, Request

logger = logging.getLogger("vitistrust")

_DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173,http://localhost:3000,https://vitistrust.vercel.app"
)

_admin_key_warning_logged = False
_verify_rate_buckets: dict[str, list[float]] = defaultdict(list)
_verify_rate_lock = Lock()


def get_cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", _DEFAULT_CORS_ORIGINS)
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    return origins or [_DEFAULT_CORS_ORIGINS.split(",")[0]]


def cors_credentials_allowed(origins: list[str] | None = None) -> bool:
    resolved = origins if origins is not None else get_cors_origins()
    return "*" not in resolved


def _verify_rate_limit_per_minute() -> int:
    return int(os.getenv("VERIFY_RATE_LIMIT_PER_MINUTE", "10"))


async def check_verify_rate_limit(request: Request) -> None:
    """In-memory per-IP rate limit for POST /verify-vineyard."""
    client_host = request.client.host if request.client else "unknown"
    limit = _verify_rate_limit_per_minute()
    now = time.monotonic()
    window_start = now - 60.0

    with _verify_rate_lock:
        bucket = _verify_rate_buckets[client_host]
        _verify_rate_buckets[client_host] = [ts for ts in bucket if ts >= window_start]
        if len(_verify_rate_buckets[client_host]) >= limit:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: max {limit} requests per minute",
            )
        _verify_rate_buckets[client_host].append(now)


def _admin_api_key_configured() -> bool:
    return bool(os.getenv("ADMIN_API_KEY", "").strip())


async def require_admin_api_key(
    x_admin_api_key: str | None = Header(default=None, alias="X-Admin-API-Key"),
) -> None:
    global _admin_key_warning_logged

    configured_key = os.getenv("ADMIN_API_KEY", "").strip()
    environment = os.getenv("ENVIRONMENT", "development").lower()
    require_key = os.getenv("REQUIRE_ADMIN_API_KEY", "false").lower() in {"1", "true", "yes"}

    if not configured_key:
        if environment == "production" or require_key:
            raise HTTPException(status_code=503, detail="Admin API key not configured")
        if not _admin_key_warning_logged:
            logger.warning(
                "ADMIN_API_KEY not set — admin endpoints allowed without authentication (dev mode)"
            )
            _admin_key_warning_logged = True
        return

    if not x_admin_api_key or x_admin_api_key != configured_key:
        raise HTTPException(status_code=401, detail="Invalid or missing admin API key")
