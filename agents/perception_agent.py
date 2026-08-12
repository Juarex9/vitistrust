# agents/perception_agent.py
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
import time

import requests

from dotenv import load_dotenv
import os

load_dotenv()

logger = logging.getLogger("vitistrust.perception")

SATELLITE_STATS_URL = "https://services.sentinel-hub.com/api/v1/statistics"
SATELLITE_PROCESS_URL = "https://services.sentinel-hub.com/api/v1/process"

_token_cache = {"token": None, "expires": 0}

STATS_EVALSCRIPT = """
//VERSION=3
function setup() {
  return {
    input: [{ bands: ["B04", "B08", "B11", "dataMask"] }],
    output: [
      { id: "ndvi", bands: 1 },
      { id: "ndmi", bands: 1 },
      { id: "dataMask", bands: 1 }
    ]
  };
}
function evaluatePixel(samples) {
  let ndvi = (samples.B08 - samples.B04) / (samples.B08 + samples.B04);
  let ndmi = (samples.B08 - samples.B11) / (samples.B08 + samples.B11);
  let valid = 1;
  if (!isFinite(ndvi) || !isFinite(ndmi)) {
    valid = 0;
  }
  return {
    ndvi: [ndvi],
    ndmi: [ndmi],
    dataMask: [samples.dataMask * valid]
  };
}
"""


def _get_sentinel_token() -> str | None:
    """Obtiene access token de Sentinel Hub OAuth."""
    global _token_cache
    now = time.time()

    if _token_cache["token"] and now < _token_cache["expires"] - 60:
        return _token_cache["token"]

    client_id = os.getenv("SENTINEL_CLIENT_ID")
    client_secret = os.getenv("SENTINEL_CLIENT_SECRET")

    if not client_id or not client_secret:
        logger.error("SENTINEL_CLIENT_ID or SENTINEL_CLIENT_SECRET not configured")
        return None

    try:
        resp = requests.post(
            "https://services.sentinel-hub.com/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            _token_cache["token"] = data["access_token"]
            _token_cache["expires"] = now + data.get("expires_in", 3600)
            return _token_cache["token"]
    except Exception as e:
        logger.error(f"Sentinel OAuth failed: {e}")

    return None


def get_real_ndvi(lat: float, lon: float, date_from: str | None = None, date_to: str | None = None) -> dict[str, Any]:
    """
    Consulta el índice NDVI de un viñedo usando Sentinel-2 via Sentinel Hub.
    """
    result = get_real_indices(lat, lon)
    if result["status"] == "success":
        return {
            "status": "success",
            "ndvi": result["ndvi"],
            "coordinates": {"lat": lat, "lon": lon},
            "source": result["source"],
        }
    return _fallback_ndvi(lat, lon)


def _extract_mean(outputs: dict[str, Any], channel: str) -> float | None:
    channel_data = outputs.get(channel, {})
    bands = channel_data.get("bands", {})
    band_data = bands.get("B0", {})
    stats = band_data.get("stats", {})
    mean = stats.get("mean")
    if mean is None:
        return None
    try:
        value = float(mean)
    except (TypeError, ValueError):
        return None
    if value != value:  # NaN
        return None
    return value


def _pick_latest_stats_interval(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Elige el intervalo más reciente con estadísticas válidas."""
    rows = payload.get("data") or []
    for row in reversed(rows):
        outputs = row.get("outputs") or {}
        ndvi = _extract_mean(outputs, "ndvi")
        ndmi = _extract_mean(outputs, "ndmi")
        if ndvi is not None and ndmi is not None:
            return {"ndvi": ndvi, "ndmi": ndmi, "interval": row.get("interval")}
    return None


def get_real_indices(lat: float, lon: float) -> dict[str, Any]:
    """Consulta NDVI + NDMI reales desde Sentinel Hub Statistical API."""
    token = _get_sentinel_token()
    if not token:
        logger.warning("No Sentinel token, using fallback NDVI/NDMI")
        return _fallback_indices(lat, lon)

    offset = 0.005
    bbox = [lon - offset, lat - offset, lon + offset, lat + offset]
    now_utc = datetime.now(timezone.utc)
    date_to = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    date_from = (now_utc - timedelta(days=180)).strftime("%Y-%m-%dT%H:%M:%SZ")

    payload = {
        "input": {
            "bounds": {
                "bbox": bbox,
                "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"},
            },
            "data": [
                {
                    "type": "sentinel-2-l2a",
                    "dataFilter": {
                        "maxCloudCoverage": 50,
                        "mosaickingOrder": "leastCC",
                    },
                }
            ],
        },
        "aggregation": {
            "timeRange": {"from": date_from, "to": date_to},
            "aggregationInterval": {"of": "P30D"},
            "width": 64,
            "height": 64,
            "evalscript": STATS_EVALSCRIPT,
        },
    }

    try:
        response = requests.post(
            SATELLITE_STATS_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=60,
        )
        if response.status_code == 401:
            logger.warning("Sentinel token expired, using fallback")
            _token_cache["token"] = None
            return _fallback_indices(lat, lon)
        if response.status_code != 200:
            logger.warning(
                "Sentinel Statistics API error: %s, using fallback",
                response.status_code,
            )
            return _fallback_indices(lat, lon)

        picked = _pick_latest_stats_interval(response.json())
        if not picked:
            logger.warning("No valid statistics intervals, using fallback")
            return _fallback_indices(lat, lon)

        return {
            "status": "success",
            "ndvi": round(max(-1.0, min(1.0, picked["ndvi"])), 3),
            "ndmi": round(max(-1.0, min(1.0, picked["ndmi"])), 3),
            "coordinates": {"lat": lat, "lon": lon},
            "source": "Sentinel-2 L2A via Sentinel Hub Statistical API",
        }
    except requests.RequestException as e:
        logger.error(f"Sentinel Hub API error: {e}")
        return _fallback_indices(lat, lon)
    except Exception as e:
        logger.error(f"Failed to parse Sentinel statistics response: {e}")
        return _fallback_indices(lat, lon)


def _fallback_ndvi(lat: float, lon: float) -> dict[str, Any]:
    """Fallback NDVI determinista basado en coordenadas (región de Mendoza)."""
    seed = int(abs(lat * lon * 1000000) % 10000)
    base_ndvi = 0.55 + (seed / 100000) - 0.05
    return {
        "status": "success",
        "ndvi": round(base_ndvi, 3),
        "coordinates": {"lat": lat, "lon": lon},
        "source": "Fallback (demo mode)",
    }


def _fallback_indices(lat: float, lon: float) -> dict[str, Any]:
    """Fallback determinista NDVI + NDMI."""
    seed = int(abs(lat * lon * 1000000) % 10000)
    base_ndvi = 0.55 + (seed / 100000) - 0.05
    base_ndmi = 0.2 + (seed / 120000) - 0.04
    return {
        "status": "success",
        "ndvi": round(base_ndvi, 3),
        "ndmi": round(base_ndmi, 3),
        "coordinates": {"lat": lat, "lon": lon},
        "source": "Fallback (demo mode)",
    }


def get_phenology_thresholds(month: int) -> dict[str, float | str]:
    """Umbrales de NDMI por etapa fenológica (hemisferio sur)."""
    if month in [9, 10]:
        return {"stage": "budbreak", "critical": 0.05, "warning": 0.12}
    if month in [11, 12]:
        return {"stage": "flowering_fruitset", "critical": 0.08, "warning": 0.16}
    if month in [1, 2]:
        return {"stage": "veraison_ripening", "critical": 0.12, "warning": 0.2}
    if month in [3, 4]:
        return {"stage": "harvest_postharvest", "critical": 0.08, "warning": 0.15}
    return {"stage": "dormancy", "critical": -0.02, "warning": 0.05}


def get_water_stress_level(ndmi: float, month: int | None = None) -> dict[str, Any]:
    """Calcula nivel de estrés hídrico usando umbrales fenológicos/estacionales."""
    month_value = month or datetime.now(timezone.utc).month
    thresholds = get_phenology_thresholds(month_value)
    if ndmi <= float(thresholds["critical"]):
        level = "critical"
    elif ndmi <= float(thresholds["warning"]):
        level = "warning"
    else:
        level = "normal"
    return {
        "level": level,
        "ndmi": round(ndmi, 3),
        "phenology_stage": thresholds["stage"],
        "thresholds": {
            "critical": thresholds["critical"],
            "warning": thresholds["warning"],
        },
    }


if __name__ == "__main__":
    print(get_real_ndvi(-33.125, -68.895))
