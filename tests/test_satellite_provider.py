"""Tests para la abstracción de proveedores satelitales (GEE / Sentinel Hub / fallback)."""

from __future__ import annotations

import asyncio

import pytest

from backend.satellite_provider import (
    FallbackSatelliteProvider,
    GeeSatelliteProvider,
    SatelliteNotConfiguredError,
    SentinelHubProvider,
    create_satellite_provider,
    is_gee_configured,
    is_sentinel_configured,
)


def _clear_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "SATELLITE_PROVIDER",
        "GEE_PROJECT_ID",
        "GEE_SERVICE_ACCOUNT_JSON",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "SENTINEL_CLIENT_ID",
        "SENTINEL_CLIENT_SECRET",
    ):
        monkeypatch.delenv(var, raising=False)


class TestIsConfiguredHelpers:
    def test_is_gee_configured_false_without_project(self, monkeypatch: pytest.MonkeyPatch):
        _clear_provider_env(monkeypatch)
        assert is_gee_configured() is False

    def test_is_gee_configured_true_with_inline_json(self, monkeypatch: pytest.MonkeyPatch):
        _clear_provider_env(monkeypatch)
        monkeypatch.setenv("GEE_PROJECT_ID", "my-gee-project")
        monkeypatch.setenv("GEE_SERVICE_ACCOUNT_JSON", '{"client_email": "sa@my-gee-project.iam"}')
        assert is_gee_configured() is True

    def test_is_gee_configured_false_with_missing_key_file(self, monkeypatch: pytest.MonkeyPatch):
        _clear_provider_env(monkeypatch)
        monkeypatch.setenv("GEE_PROJECT_ID", "my-gee-project")
        monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/nonexistent/path/sa.json")
        assert is_gee_configured() is False

    def test_is_sentinel_configured_requires_both_vars(self, monkeypatch: pytest.MonkeyPatch):
        _clear_provider_env(monkeypatch)
        monkeypatch.setenv("SENTINEL_CLIENT_ID", "client-id")
        assert is_sentinel_configured() is False
        monkeypatch.setenv("SENTINEL_CLIENT_SECRET", "client-secret")
        assert is_sentinel_configured() is True


class TestCreateSatelliteProviderFactory:
    def test_auto_without_any_config_falls_back_to_demo(self, monkeypatch: pytest.MonkeyPatch):
        _clear_provider_env(monkeypatch)
        provider = create_satellite_provider()
        assert isinstance(provider, FallbackSatelliteProvider)
        assert provider.name == "fallback"

    def test_auto_with_sentinel_credentials_uses_sentinel(self, monkeypatch: pytest.MonkeyPatch):
        _clear_provider_env(monkeypatch)
        monkeypatch.setenv("SENTINEL_CLIENT_ID", "client-id")
        monkeypatch.setenv("SENTINEL_CLIENT_SECRET", "client-secret")
        provider = create_satellite_provider()
        assert isinstance(provider, SentinelHubProvider)
        assert provider.name == "sentinel"

    def test_auto_with_gee_credentials_prefers_gee(self, monkeypatch: pytest.MonkeyPatch):
        _clear_provider_env(monkeypatch)
        monkeypatch.setenv("GEE_PROJECT_ID", "my-gee-project")
        monkeypatch.setenv("GEE_SERVICE_ACCOUNT_JSON", '{"client_email": "sa@my-gee-project.iam"}')
        monkeypatch.setenv("SENTINEL_CLIENT_ID", "client-id")
        monkeypatch.setenv("SENTINEL_CLIENT_SECRET", "client-secret")
        provider = create_satellite_provider()
        assert isinstance(provider, GeeSatelliteProvider)
        assert provider.name == "gee"

    def test_explicit_provider_gee_overrides_auto_detection(self, monkeypatch: pytest.MonkeyPatch):
        _clear_provider_env(monkeypatch)
        monkeypatch.setenv("SATELLITE_PROVIDER", "gee")
        provider = create_satellite_provider()
        assert isinstance(provider, GeeSatelliteProvider)

    def test_explicit_provider_sentinel_overrides_auto_detection(self, monkeypatch: pytest.MonkeyPatch):
        _clear_provider_env(monkeypatch)
        monkeypatch.setenv("SATELLITE_PROVIDER", "sentinel")
        provider = create_satellite_provider()
        assert isinstance(provider, SentinelHubProvider)

    def test_unknown_provider_value_falls_back_to_auto(self, monkeypatch: pytest.MonkeyPatch):
        _clear_provider_env(monkeypatch)
        monkeypatch.setenv("SATELLITE_PROVIDER", "not-a-real-provider")
        provider = create_satellite_provider()
        assert isinstance(provider, FallbackSatelliteProvider)


class TestGeeSatelliteProviderNotConfigured:
    def test_fetch_indices_raises_not_configured_without_project_id(self, monkeypatch: pytest.MonkeyPatch):
        _clear_provider_env(monkeypatch)
        GeeSatelliteProvider._ee_initialized = False
        provider = GeeSatelliteProvider()

        with pytest.raises(SatelliteNotConfiguredError):
            asyncio.run(provider.fetch_indices(-33.1234, -68.9876))

    def test_fetch_indices_raises_not_configured_without_credentials(self, monkeypatch: pytest.MonkeyPatch):
        _clear_provider_env(monkeypatch)
        monkeypatch.setenv("GEE_PROJECT_ID", "my-gee-project")
        GeeSatelliteProvider._ee_initialized = False
        provider = GeeSatelliteProvider()

        with pytest.raises(SatelliteNotConfiguredError):
            asyncio.run(provider.fetch_indices(-33.1234, -68.9876))

    def test_fetch_history_raises_not_configured_without_project_id(self, monkeypatch: pytest.MonkeyPatch):
        _clear_provider_env(monkeypatch)
        GeeSatelliteProvider._ee_initialized = False
        provider = GeeSatelliteProvider()

        with pytest.raises(SatelliteNotConfiguredError):
            asyncio.run(provider.fetch_history(-33.1234, -68.9876, 6))

    def test_fetch_layer_image_raises_not_configured_without_project_id(self, monkeypatch: pytest.MonkeyPatch):
        _clear_provider_env(monkeypatch)
        GeeSatelliteProvider._ee_initialized = False
        provider = GeeSatelliteProvider()

        with pytest.raises(SatelliteNotConfiguredError):
            asyncio.run(provider.fetch_layer_image(-33.1234, -68.9876, 0.6, "ndvi"))


class TestFallbackSatelliteProvider:
    def test_fetch_indices_is_deterministic(self):
        provider = FallbackSatelliteProvider()
        first = asyncio.run(provider.fetch_indices(-33.1234, -68.9876))
        second = asyncio.run(provider.fetch_indices(-33.1234, -68.9876))

        assert first == second
        assert first["status"] == "success"
        assert "Fallback" in first["source"]
        assert -1.0 <= first["ndvi"] <= 1.0
        assert -1.0 <= first["ndmi"] <= 1.0

    def test_fetch_history_marks_demo_true(self):
        provider = FallbackSatelliteProvider()
        history = asyncio.run(provider.fetch_history(-33.1234, -68.9876, 6))

        assert len(history) == 6
        for point in history:
            assert point["demo"] is True
            assert {"date", "ndvi", "status"}.issubset(point.keys())

    def test_fetch_layer_image_returns_data_uri(self):
        provider = FallbackSatelliteProvider()
        image = asyncio.run(provider.fetch_layer_image(-33.1234, -68.9876, 0.6, "ndvi"))
        assert image.startswith("data:image/")


class TestSentinelHubProviderFallback:
    def test_fetch_indices_without_credentials_falls_back(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("SENTINEL_CLIENT_ID", raising=False)
        monkeypatch.delenv("SENTINEL_CLIENT_SECRET", raising=False)
        provider = SentinelHubProvider()
        result = asyncio.run(provider.fetch_indices(-33.1234, -68.9876))

        assert result["status"] == "success"
        assert "Fallback" in result["source"]

    def test_fetch_history_marks_demo_true(self):
        provider = SentinelHubProvider()
        history = asyncio.run(provider.fetch_history(-33.1234, -68.9876, 4))

        assert len(history) == 4
        assert all(point["demo"] is True for point in history)
