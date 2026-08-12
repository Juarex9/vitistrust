"""Tests for CORS helpers, rate limiting, and admin API key auth."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.security import (
    check_verify_rate_limit,
    cors_credentials_allowed,
    get_cors_origins,
    require_admin_api_key,
)


def test_get_cors_origins_default():
    origins = get_cors_origins()
    assert "http://localhost:5173" in origins
    assert "*" not in origins
    assert cors_credentials_allowed(origins) is True


def test_cors_credentials_disabled_with_wildcard(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CORS_ORIGINS", "*")
    origins = get_cors_origins()
    assert origins == ["*"]
    assert cors_credentials_allowed(origins) is False


def _fake_request(ip: str = "1.2.3.4") -> Request:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/verify-vineyard",
        "raw_path": b"/verify-vineyard",
        "query_string": b"",
        "headers": [],
        "client": (ip, 12345),
        "server": ("testserver", 80),
    }
    return Request(scope)


def test_verify_rate_limit_blocks_after_threshold(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("VERIFY_RATE_LIMIT_PER_MINUTE", "3")
    # Isolate buckets by unique IP
    req = _fake_request("9.9.9.9")
    for _ in range(3):
        asyncio.run(check_verify_rate_limit(req))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(check_verify_rate_limit(req))
    assert exc.value.status_code == 429


def test_admin_api_key_required_when_configured(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ADMIN_API_KEY", "secret-admin")
    monkeypatch.setenv("ENVIRONMENT", "development")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_admin_api_key(x_admin_api_key=None))
    assert exc.value.status_code == 401

    asyncio.run(require_admin_api_key(x_admin_api_key="secret-admin"))


def test_admin_api_key_required_in_production_without_config(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ADMIN_API_KEY", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_admin_api_key(x_admin_api_key=None))
    assert exc.value.status_code == 503
