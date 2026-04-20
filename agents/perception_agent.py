# agents/perception_agent.py
import logging
from datetime import datetime, timezone
from typing import Any
import time

import requests

from dotenv import load_dotenv
import os
from backend.time_window import build_time_window

load_dotenv()

logger = logging.getLogger("vitistrust.perception")

SATELLITE_STATS_URL = "https://services.sentinel-hub.com/api/v1/statistics"

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
    """Consulta NDVI + NDMI reales desde Sentinel Hub Statistics API."""
    token = _get_sentinel_token()
    if not token:
        logger.warning("No Sentinel token, using fallback NDVI/NDMI")
        return _fallback_indices(lat, lon)

    offset = 0.0005
    bbox = [lon - offset, lat - offset, lon + offset, lat + offset]
    now_utc = datetime.now(timezone.utc)
    date_to = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    date_from = (now_utc.replace(hour=0, minute=0, second=0, microsecond=0)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
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
        "aggregation": {
            "timeRange": {"from": date_from, "to": date_to},
            "aggregationInterval": {"of": "P1D"},
            "resx": 10,
            "resy": 10,
            "evalscript": """
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
                function evaluatePixel(sample) {
                  const ndvi = (sample.B08 - sample.B04) / (sample.B08 + sample.B04);
                  const ndmi = (sample.B08 - sample.B11) / (sample.B08 + sample.B11);
                  return {
                    ndvi: [ndvi],
                    ndmi: [ndmi],
                    dataMask: [sample.dataMask]
                  };
                }
            """,
        },
        "calculations": {
            "ndvi": {"statistics": {"default": {"percentiles": {"k": [5, 50, 95]}}}},
            "ndmi": {"statistics": {"default": {"percentiles": {"k": [5, 50, 95]}}}},
        },
    }

    try:
        response = requests.post(
            SATELLITE_STATS_URL,
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
        )
        if response.status_code == 401:
            logger.warning("Sentinel token expired, using fallback")
            _token_cache["token"] = None
            return _fallback_indices(lat, lon)
        response.raise_for_status()
        data = response.json()
        entries = data.get("data", [])
        if not entries:
            logger.warning("No Sentinel statistics data, using fallback")
            return _fallback_indices(lat, lon)

        outputs = entries[-1].get("outputs", {})
        ndvi = _extract_mean(outputs, "ndvi")
        ndmi = _extract_mean(outputs, "ndmi")
        if ndvi is None or ndmi is None:
            logger.warning("Unable to parse NDVI/NDMI from Sentinel response")
            return _fallback_indices(lat, lon)

        return {
            "status": "success",
            "ndvi": round(ndvi, 3),
            "ndmi": round(ndmi, 3),
            "coordinates": {"lat": lat, "lon": lon},
            "source": "Sentinel-2 L2A via Sentinel Hub Statistics API",
        }
    except requests.RequestException as e:
        logger.error(f"Sentinel Hub API error: {e}")
        return _fallback_indices(lat, lon)
    except (KeyError, IndexError, TypeError, ValueError) as e:
        logger.error(f"Failed to parse Sentinel statistics response: {e}")
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
    
    requested_from, requested_to = (date_from, date_to) if date_from and date_to else build_time_window(180)
    fallback_from, fallback_to = build_time_window(365)
    windows: list[tuple[str, str, str]] = [
        (requested_from, requested_to, "requested"),
        (fallback_from, fallback_to, "fallback-expanded"),
    ]

    for date_from_value, date_to_value, window_label in windows:
        payload = {
            "input": {
                "bounds": {"bbox": bbox},
                "data": [{
                    "type": "sentinel-2-l2a",
                    "dataFilter": {
                        "timeRange": {
                            "from": date_from_value,
                            "to": date_to_value
                        },
                        "maxCloudCoverage": 50
                    }
                }]
            },
            "aggregation": {
                "evalscript": """
                    //VERSION=3
                    function setup() {
                      return {
                        input: [{ bands: ["B04", "B08"] }],
                        output: { id: "default", bands: 1 }
                      };
                    }
                    function evaluatePixel(samples) {
                      let ndvi = (samples.B08 - samples.B04) / (samples.B08 + samples.B04);
                      return [ndvi];
                    }
                """,
                "resampling": "BILINEAR",
                "pixelBounds": [10, 10]
            }
        }

        logger.info(
            "NDVI query window=%s from=%s to=%s lat=%s lon=%s",
            window_label,
            date_from_value,
            date_to_value,
            lat,
            lon,
        )

        try:
            response = requests.post(
                SATELLITE_STATS_URL,
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
                timeout=60
            )
            
            if response.status_code == 401:
                logger.warning("Sentinel token expired, using fallback")
                _token_cache["token"] = None
                return _fallback_ndvi(lat, lon)
            
            response.raise_for_status()
            data = response.json()
            
            if "data" not in data or len(data.get("data", [])) == 0:
                logger.warning(
                    "No data from Sentinel for window=%s from=%s to=%s",
                    window_label,
                    date_from_value,
                    date_to_value,
                )
                continue
            
            avg_ndvi = data["data"][0]["outputs"]["default"]["bands"]["B0"]["stats"]["mean"]
            
            return {
                "status": "success",
                "ndvi": round(avg_ndvi, 3),
                "coordinates": {"lat": lat, "lon": lon},
                "source": "Sentinel-2 L2A via Sentinel Hub",
                "time_window": {"from": date_from_value, "to": date_to_value, "window": window_label}
            }
        except requests.RequestException as e:
            logger.error(f"Sentinel Hub API error: {e}")
            return _fallback_ndvi(lat, lon)
        except (KeyError, IndexError, TypeError) as e:
            logger.error(f"Failed to parse response: {e}")
            return _fallback_ndvi(lat, lon)

    logger.warning("No data from Sentinel after expanded window, using fallback")
    return _fallback_ndvi(lat, lon)


def _fallback_ndvi(lat: float, lon: float) -> dict[str, Any]:
    """Fallback NDVI determinista basado en coordenadas (región de Mendoza)."""
    # Usar hash de coords para obtener seed determinista
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
