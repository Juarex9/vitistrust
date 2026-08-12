"""Abstracción de proveedores satelitales (Google Earth Engine / Sentinel Hub).

Patrón inspirado en zafra-ai (`satelital/client.py`), adaptado a VitisTrust:
    - `fetch_indices`: NDVI/NDMI puntuales para un lat/lon.
    - `fetch_history`: histórico mensual de NDVI.
    - `fetch_layer_image`: imagen (data URI o URL) de una capa (ndvi/ndmi/truecolor).

`GeeSatelliteProvider` es el proveedor primario (Sentinel-2 vía Google Earth
Engine). `SentinelHubProvider` reutiliza la integración Sentinel Hub existente
como fallback, y `FallbackSatelliteProvider` es el último recurso determinista
para demos sin credenciales configuradas.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger("vitistrust.satellite_provider")

GEE_S2_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"
GEE_MAX_CLOUD_PCT = 30
GEE_LOOKBACK_DAYS = 60
GEE_AOI_BUFFER_M = 250
GEE_SOURCE_LABEL = "sentinel-2-gee"


class SatelliteNotConfiguredError(Exception):
    """El proveedor satelital no está configurado (faltan credenciales/project)."""


class SatelliteProviderError(Exception):
    """Error al consultar o procesar datos satelitales."""


@runtime_checkable
class SatelliteProvider(Protocol):
    """Contrato común para proveedores satelitales."""

    name: str

    async def fetch_indices(self, lat: float, lon: float) -> dict[str, Any]:
        """Devuelve NDVI/NDMI puntuales: status, ndvi, ndmi, coordinates, source, ..."""
        ...

    async def fetch_history(self, lat: float, lon: float, months: int) -> list[dict[str, Any]]:
        """Devuelve histórico mensual: date, ndvi, status, monthly_change, moving_avg_3m."""
        ...

    async def fetch_layer_image(self, lat: float, lon: float, ndvi: float, layer: str = "ndvi") -> str:
        """Devuelve una data URI o URL embebible para la capa solicitada."""
        ...


def _ndvi_status(ndvi: float) -> str:
    if ndvi > 0.6:
        return "healthy"
    if ndvi > 0.4:
        return "moderate"
    return "stressed"


def _shift_months(dt: datetime, delta: int) -> datetime:
    """Suma/resta meses calendario (no días) a una fecha, normalizando al día 1."""
    month_index = dt.month - 1 + delta
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    return dt.replace(year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0)


def is_gee_configured() -> bool:
    """Indica si hay configuración mínima para intentar Earth Engine."""
    project_id = os.getenv("GEE_PROJECT_ID", "").strip()
    if not project_id:
        return False
    key_data = os.getenv("GEE_SERVICE_ACCOUNT_JSON", "").strip()
    if key_data.startswith("{"):
        return True
    key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    return bool(key_path and os.path.isfile(key_path))


def is_sentinel_configured() -> bool:
    """Indica si hay credenciales OAuth de Sentinel Hub configuradas."""
    return bool(
        os.getenv("SENTINEL_CLIENT_ID", "").strip()
        and os.getenv("SENTINEL_CLIENT_SECRET", "").strip()
    )


class GeeSatelliteProvider:
    """Proveedor primario: Sentinel-2 vía Google Earth Engine."""

    name = "gee"
    _ee_initialized = False

    def _ensure_initialized(self) -> None:
        if GeeSatelliteProvider._ee_initialized:
            return

        project_id = os.getenv("GEE_PROJECT_ID", "").strip()
        if not project_id:
            raise SatelliteNotConfiguredError(
                "GEE_PROJECT_ID es obligatorio. Registrá el proyecto en Earth Engine."
            )

        try:
            import ee
        except ImportError as exc:
            raise SatelliteNotConfiguredError(
                "Instalá earthengine-api: pip install earthengine-api"
            ) from exc

        credentials = None
        key_data = os.getenv("GEE_SERVICE_ACCOUNT_JSON", "").strip()
        key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()

        if key_data.startswith("{"):
            try:
                info = json.loads(key_data)
            except json.JSONDecodeError as exc:
                raise SatelliteNotConfiguredError(
                    "GEE_SERVICE_ACCOUNT_JSON no es un JSON válido"
                ) from exc
            email = info.get("client_email")
            if not email:
                raise SatelliteNotConfiguredError("JSON de service account sin client_email")
            credentials = ee.ServiceAccountCredentials(email, key_data=key_data)
        elif key_path:
            credentials = ee.ServiceAccountCredentials(None, key_file=key_path)
        else:
            raise SatelliteNotConfiguredError(
                "Configurá GEE_SERVICE_ACCOUNT_JSON o GOOGLE_APPLICATION_CREDENTIALS."
            )

        try:
            ee.Initialize(credentials, project=project_id)
        except Exception as exc:
            logger.error("Fallo al inicializar Earth Engine: %s", exc)
            raise SatelliteNotConfiguredError(
                "No se pudo autenticar en Earth Engine. Revisá las credenciales del "
                "service account y GEE_PROJECT_ID."
            ) from exc

        GeeSatelliteProvider._ee_initialized = True
        logger.info("Earth Engine inicializado (project=%s)", project_id)

    @staticmethod
    def _aoi(ee_mod: Any, lat: float, lon: float) -> Any:
        return ee_mod.Geometry.Point([lon, lat]).buffer(GEE_AOI_BUFFER_M).bounds()

    @staticmethod
    def _recent_collection(ee_mod: Any, aoi: Any, days_back: int = GEE_LOOKBACK_DAYS) -> Any:
        end = datetime.now(UTC)
        start = end - timedelta(days=days_back)
        return (
            ee_mod.ImageCollection(GEE_S2_COLLECTION)
            .filterBounds(aoi)
            .filterDate(start.isoformat(), end.isoformat())
            .filter(ee_mod.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", GEE_MAX_CLOUD_PCT))
        )

    def _fetch_indices_sync(self, lat: float, lon: float) -> dict[str, Any]:
        self._ensure_initialized()
        import ee

        aoi = self._aoi(ee, lat, lon)
        collection = self._recent_collection(ee, aoi).sort("system:time_start", False)

        count = collection.size().getInfo()
        if not count:
            raise SatelliteProviderError(
                f"Sin escenas Sentinel-2 con nubes < {GEE_MAX_CLOUD_PCT}% "
                f"en los últimos {GEE_LOOKBACK_DAYS} días cerca del punto."
            )

        image = ee.Image(collection.first())
        ndvi_img = image.normalizedDifference(["B8", "B4"]).rename("NDVI")
        ndmi_img = image.normalizedDifference(["B8", "B11"]).rename("NDMI")
        indexed = image.addBands([ndvi_img, ndmi_img])

        stats = (
            indexed.select(["NDVI", "NDMI"])
            .reduceRegion(reducer=ee.Reducer.mean(), geometry=aoi, scale=10, maxPixels=1e9)
            .getInfo()
        )

        ndvi_value = stats.get("NDVI")
        ndmi_value = stats.get("NDMI")
        if ndvi_value is None or ndmi_value is None:
            raise SatelliteProviderError(
                "Earth Engine no devolvió NDVI/NDMI válidos para el área consultada."
            )

        captured_ms = image.get("system:time_start").getInfo()
        captured_at = datetime.fromtimestamp(captured_ms / 1000, tz=UTC).isoformat()
        cloud_pct = image.get("CLOUDY_PIXEL_PERCENTAGE").getInfo()

        return {
            "status": "success",
            "ndvi": round(max(-1.0, min(1.0, float(ndvi_value))), 3),
            "ndmi": round(max(-1.0, min(1.0, float(ndmi_value))), 3),
            "coordinates": {"lat": lat, "lon": lon},
            "source": GEE_SOURCE_LABEL,
            "cloud_coverage": float(cloud_pct) if cloud_pct is not None else None,
            "captured_at": captured_at,
        }

    async def fetch_indices(self, lat: float, lon: float) -> dict[str, Any]:
        return await asyncio.to_thread(self._fetch_indices_sync, lat, lon)

    def _fetch_history_sync(self, lat: float, lon: float, months: int) -> list[dict[str, Any]]:
        self._ensure_initialized()
        import ee

        safe_months = max(1, min(int(months), 24))
        aoi = self._aoi(ee, lat, lon)
        anchor = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        history: list[dict[str, Any]] = []
        for offset in range(safe_months - 1, -1, -1):
            month_start = _shift_months(anchor, -offset)
            month_end = _shift_months(month_start, 1)

            monthly_collection = (
                ee.ImageCollection(GEE_S2_COLLECTION)
                .filterBounds(aoi)
                .filterDate(month_start.isoformat(), month_end.isoformat())
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", GEE_MAX_CLOUD_PCT))
            )

            scene_count = monthly_collection.size().getInfo()
            if not scene_count:
                continue

            ndvi_collection = monthly_collection.map(
                lambda img: img.normalizedDifference(["B8", "B4"]).rename("NDVI")
            )
            stats = (
                ndvi_collection.mean()
                .reduceRegion(reducer=ee.Reducer.mean(), geometry=aoi, scale=10, maxPixels=1e9)
                .getInfo()
            )
            ndvi_value = stats.get("NDVI")
            if ndvi_value is None:
                continue

            ndvi_value = max(0.0, min(1.0, float(ndvi_value)))
            history.append(
                {
                    "date": month_start.strftime("%Y-%m"),
                    "ndvi": round(ndvi_value, 3),
                    "status": _ndvi_status(ndvi_value),
                    "scene_count": int(scene_count),
                    "demo": False,
                }
            )

        if not history:
            raise SatelliteProviderError(
                "Sin escenas Sentinel-2 disponibles para el histórico solicitado."
            )

        from backend.satellite_ops import _enrich_history

        return _enrich_history(history)

    async def fetch_history(self, lat: float, lon: float, months: int) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._fetch_history_sync, lat, lon, months)

    def _fetch_layer_image_sync(self, lat: float, lon: float, ndvi: float, layer: str) -> str:
        self._ensure_initialized()
        import ee

        aoi = self._aoi(ee, lat, lon)
        collection = self._recent_collection(ee, aoi).sort("system:time_start", False)
        count = collection.size().getInfo()
        if not count:
            raise SatelliteProviderError("Sin escenas recientes para generar la imagen satelital.")

        image = ee.Image(collection.first())

        if layer == "ndmi":
            index_img = image.normalizedDifference(["B8", "B11"]).rename("NDMI")
            vis = index_img.visualize(
                min=-0.3,
                max=0.6,
                palette=["8b0000", "c89632", "64b4c8", "3264b4", "003264"],
            )
        elif layer == "truecolor":
            vis = image.visualize(bands=["B4", "B3", "B2"], min=0, max=3000)
        else:
            index_img = image.normalizedDifference(["B8", "B4"]).rename("NDVI")
            vis = index_img.visualize(min=0.0, max=0.9, palette=["8b0000", "ffff00", "006400"])

        clipped = vis.clip(aoi)
        try:
            url = clipped.getThumbURL({"region": aoi, "dimensions": 512, "format": "png"})
        except Exception as exc:
            raise SatelliteProviderError(f"No se pudo generar thumbnail GEE: {exc}") from exc
        return url

    async def fetch_layer_image(self, lat: float, lon: float, ndvi: float, layer: str = "ndvi") -> str:
        return await asyncio.to_thread(self._fetch_layer_image_sync, lat, lon, ndvi, layer)


class SentinelHubProvider:
    """Proveedor secundario: reutiliza la integración Sentinel Hub existente."""

    name = "sentinel"

    async def fetch_indices(self, lat: float, lon: float) -> dict[str, Any]:
        from agents.perception_agent import get_real_indices

        return await asyncio.to_thread(get_real_indices, lat, lon)

    async def fetch_history(self, lat: float, lon: float, months: int) -> list[dict[str, Any]]:
        from backend.satellite_ops import _build_ndvi_history

        history = await asyncio.to_thread(_build_ndvi_history, lat, lon, months)
        for point in history:
            point.setdefault("demo", True)
        return history

    async def fetch_layer_image(self, lat: float, lon: float, ndvi: float, layer: str = "ndvi") -> str:
        from backend.satellite_ops import _get_satellite_image_base64

        return await _get_satellite_image_base64(lat, lon, ndvi, layer=layer)


class FallbackSatelliteProvider:
    """Último recurso determinista, usado cuando no hay GEE ni Sentinel Hub configurados."""

    name = "fallback"

    async def fetch_indices(self, lat: float, lon: float) -> dict[str, Any]:
        from agents.perception_agent import _fallback_indices

        return await asyncio.to_thread(_fallback_indices, lat, lon)

    async def fetch_history(self, lat: float, lon: float, months: int) -> list[dict[str, Any]]:
        from backend.satellite_ops import _build_ndvi_history

        history = await asyncio.to_thread(_build_ndvi_history, lat, lon, months)
        for point in history:
            point.setdefault("demo", True)
        return history

    async def fetch_layer_image(self, lat: float, lon: float, ndvi: float, layer: str = "ndvi") -> str:
        from backend.satellite_ops import _get_satellite_image_base64

        return await _get_satellite_image_base64(lat, lon, ndvi, layer=layer)


def create_satellite_provider() -> SatelliteProvider:
    """Factory: elige el proveedor satelital según `SATELLITE_PROVIDER` (gee|sentinel|auto)."""
    mode = os.getenv("SATELLITE_PROVIDER", "auto").strip().lower()

    if mode == "gee":
        return GeeSatelliteProvider()
    if mode == "sentinel":
        return SentinelHubProvider()
    if mode not in ("auto", ""):
        logger.warning("SATELLITE_PROVIDER desconocido (%s), usando modo auto", mode)

    if is_gee_configured():
        logger.info("Satellite provider (auto): GEE configurado, usando GeeSatelliteProvider")
        return GeeSatelliteProvider()
    if is_sentinel_configured():
        logger.info("Satellite provider (auto): usando SentinelHubProvider")
        return SentinelHubProvider()

    logger.warning(
        "Satellite provider (auto): sin GEE ni Sentinel Hub configurados, usando fallback demo"
    )
    return FallbackSatelliteProvider()
