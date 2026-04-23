# agents/perception_agent.py
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
import time

import requests

from dotenv import load_dotenv
import os
from backend.time_window import build_time_window

load_dotenv()

logger = logging.getLogger("vitistrust.perception")

SATELLITE_STATS_URL = "https://services.sentinel-hub.com/api/v1/statistics"
SATELLITE_PROCESS_URL = "https://services.sentinel-hub.com/api/v1/process"

_token_cache = {"token": None, "expires": 0}


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
            timeout=15
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
    
    Args:
        lat: Latitud de la parcela
        lon: Longitud de la parcela
        
    Returns:
        Dict con status, ndvi, coordinates, source
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


def get_real_indices(lat: float, lon: float) -> dict[str, Any]:
    """Consulta NDVI + NDMI reales desde Sentinel Hub Process API."""
    token = _get_sentinel_token()
    if not token:
        logger.warning("No Sentinel token, using fallback NDVI/NDMI")
        return _fallback_indices(lat, lon)

    offset = 0.005
    bbox = [lon - offset, lat - offset, lon + offset, lat + offset]
    now_utc = datetime.now(timezone.utc)
    date_to = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    date_from = (now_utc - timedelta(days=180)).strftime("%Y-%m-%dT%H:%M:%SZ")

    evalscript = """
    //VERSION=3
    function setup() {
        return {
            input: ["B04", "B08", "B11", "dataMask"],
            output: { id: "default", bands: 3 }
        };
    }
    function evaluatePixel(sample) {
        if (sample.dataMask === 0) return [0, 0, 0];
        let ndvi = (sample.B08 - sample.B04) / (sample.B08 + sample.B04);
        let ndmi = (sample.B08 - sample.B11) / (sample.B08 + sample.B11);
        return [ndvi, ndmi, sample.dataMask];
    }
    """

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
                        "timeRange": {"from": date_from, "to": date_to},
                        "maxCloudCoverage": 50,
                    },
                }
            ],
        },
        "output": {"responses": [{"identifier": "default", "format": {"type": "image/png"}}]},
        "evalscript": evalscript,
    }

    try:
        response = requests.post(
            SATELLITE_PROCESS_URL,
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
        )
        if response.status_code == 401:
            logger.warning("Sentinel token expired, using fallback")
            _token_cache["token"] = None
            return _fallback_indices(lat, lon)
        if response.status_code != 200 or len(response.content) < 1000:
            logger.warning(f"Sentinel Process API error: {response.status_code}, using fallback")
            return _fallback_indices(lat, lon)

        img_data = response.content
        ndvi_vals = []
        ndmi_vals = []

        for y in range(0, min(512, len(img_data) // 4), 10):
            for x in range(0, min(512, len(img_data) // 4), 10):
                idx = (y * 512 + x) * 4
                if idx + 2 < len(img_data):
                    r, g, b = img_data[idx], img_data[idx + 1], img_data[idx + 2]
                    ndvi_sample = (r - b) / (r + b) if (r + b) > 0 else 0
                    ndmi_sample = (r - g) / (r + g) if (r + g) > 0 else 0
                    if abs(ndvi_sample) < 1.0 and abs(ndmi_sample) < 1.0:
                        ndvi_vals.append(ndvi_sample)
                        ndmi_vals.append(ndmi_sample)

        if not ndvi_vals:
            logger.warning("No valid pixels from Process API, using fallback")
            return _fallback_indices(lat, lon)

        ndvi = sum(ndvi_vals) / len(ndvi_vals)
        ndmi = sum(ndmi_vals) / len(ndmi_vals)

        return {
            "status": "success",
            "ndvi": round(ndvi, 3),
            "ndmi": round(ndmi, 3),
            "coordinates": {"lat": lat, "lon": lon},
            "source": "Sentinel-2 L2A via Sentinel Hub Process API",
        }
    except requests.RequestException as e:
        logger.error(f"Sentinel Hub API error: {e}")
        return _fallback_indices(lat, lon)
    except Exception as e:
        logger.error(f"Failed to parse Sentinel response: {e}")
        return _fallback_indices(lat, lon)


def _extract_mean(outputs: dict[str, Any], channel: str) -> float | None:
    channel_data = outputs.get(channel, {})
    bands = channel_data.get("bands", {})
    band_data = bands.get("B0", {})
    stats = band_data.get("stats", {})
    mean = stats.get("mean")
    if mean is None:
        return None
    return float(mean)


def _fallback_ndvi(lat: float, lon: float) -> dict[str, Any]:
    """Fallback NDVI determinista basado en coordenadas (región de Mendoza)."""
    seed = int(abs(lat * lon * 1000000) % 10000)
    base_ndvi = 0.55 + (seed / 100000) - 0.05
    return {
        "status": "success",
        "ndvi": round(base_ndvi, 3),
        "coordinates": {"lat": lat, "lon": lon},
        "source": "Fallback (demo mode)"
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
