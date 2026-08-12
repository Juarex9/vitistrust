"""Satellite image and history API routes."""

import base64
import logging

from fastapi import APIRouter, Query
from fastapi.responses import Response

from backend import deps
from backend.satellite_ops import (
    NDMI_EVALSCRIPT,
    NDVI_EVALSCRIPT,
    TRUE_COLOR_EVALSCRIPT,
    _build_ndvi_history,
    _evaluate_alerts,
    _fetch_sentinel_image,
    _generate_placeholder_svg,
    _get_sentinel_token,
    _resolve_window,
)
from backend.satellite_provider import SatelliteNotConfiguredError, SatelliteProviderError

logger = logging.getLogger("vitistrust")

router = APIRouter()


@router.get("/satellite-image")
async def satellite_image(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    layer: str = Query("ndvi", description="Layer type: ndvi, ndmi, truecolor"),
    date: str = Query(None, description="Date for historical image (YYYY-MM-DD)"),
    from_: str | None = Query(None, alias="from", description="ISO datetime start (e.g. 2026-01-01T00:00:00Z)"),
    to: str | None = Query(None, description="ISO datetime end (e.g. 2026-04-20T23:59:59Z)"),
):
    """Proxy que devuelve la imagen satelital con diferentes capas."""
    date_from, date_to = _resolve_window(date=date, from_param=from_, to_param=to)
    logger.info("satellite_image effective window from=%s to=%s lat=%s lon=%s", date_from, date_to, lat, lon)

    evalscript = NDVI_EVALSCRIPT
    if layer == "ndmi":
        evalscript = NDMI_EVALSCRIPT
    elif layer == "truecolor":
        evalscript = TRUE_COLOR_EVALSCRIPT

    token = await _get_sentinel_token()
    ndvi_value = 0.55

    if token:
        image_bytes = await _fetch_sentinel_image(token, lat, lon, evalscript, date_from, date_to)
        if image_bytes:
            return Response(content=image_bytes, media_type="image/png")
        logger.warning("Sentinel image fetch returned no data, using placeholder")

    svg_bytes = _generate_placeholder_svg(lat, lon, ndvi_value, layer)
    return Response(content=svg_bytes, media_type="image/svg+xml")


@router.get("/satellite/layers")
async def satellite_layers(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    from_: str | None = Query(None, alias="from", description="ISO datetime start"),
    to: str | None = Query(None, description="ISO datetime end"),
) -> dict:
    """Devuelve las diferentes capas satelitales (NDVI, NDMI, TrueColor)."""
    layers = {}
    evalscripts = {
        "ndvi": NDVI_EVALSCRIPT,
        "ndmi": NDMI_EVALSCRIPT,
        "truecolor": TRUE_COLOR_EVALSCRIPT,
    }

    date_from, date_to = _resolve_window(from_param=from_, to_param=to)
    logger.info("satellite_layers effective window from=%s to=%s lat=%s lon=%s", date_from, date_to, lat, lon)

    token = await _get_sentinel_token()

    for layer_name, evalscript in evalscripts.items():
        if token:
            image_bytes = await _fetch_sentinel_image(
                token, lat, lon, evalscript, date_from, date_to
            )
            if image_bytes:
                b64 = base64.b64encode(image_bytes).decode()
                layers[layer_name] = f"data:image/png;base64,{b64}"
                continue

        fallback_svg = _generate_placeholder_svg(lat, lon, 0.55, layer_name)
        layers[layer_name] = f"data:image/svg+xml;base64,{base64.b64encode(fallback_svg).decode()}"

    return {"layers": layers, "coordinates": {"lat": lat, "lon": lon}}


@router.get("/satellite/history")
async def satellite_history(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    months: int = Query(24, description="Number of months to look back"),
) -> dict:
    """Devuelve el historial NDVI de los últimos N meses.

    Usa el proveedor satelital activo (GEE si está configurado); si el
    proveedor no está disponible o falla, cae a un histórico sintético
    determinista (`source: synthetic_demo`, `demo: true`).
    """
    provider = deps.satellite_provider
    history: list[dict] = []
    is_real = False

    if provider is not None:
        try:
            history = await provider.fetch_history(lat, lon, months)
            is_real = provider.name == "gee" and bool(history)
        except (SatelliteNotConfiguredError, SatelliteProviderError) as exc:
            logger.warning(
                "Proveedor satelital (%s) no pudo generar histórico, usando sintético: %s",
                provider.name,
                exc,
            )
        except Exception as exc:
            logger.error("Error inesperado obteniendo histórico satelital: %s", exc)

    if not history:
        history = _build_ndvi_history(lat, lon, months)
        is_real = False

    alerts = _evaluate_alerts(history)

    return {
        "history": history,
        "alerts": alerts,
        "coordinates": {"lat": lat, "lon": lon},
        "months_analyzed": len(history),
        "source": "sentinel-2-gee" if is_real else "synthetic_demo",
        "demo": not is_real,
    }
