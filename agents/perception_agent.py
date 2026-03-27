# agents/perception_agent.py
import logging
from typing import Any
import time

import requests

from dotenv import load_dotenv
import os

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


def get_real_ndvi(lat: float, lon: float) -> dict[str, Any]:
    """
    Consulta el índice NDVI de un viñedo usando Sentinel-2 via Sentinel Hub.
    
    Args:
        lat: Latitud de la parcela
        lon: Longitud de la parcela
        
    Returns:
        Dict con status, ndvi, coordinates, source
    """
    token = _get_sentinel_token()
    
    if not token:
        logger.warning("No Sentinel token, using fallback NDVI")
        return _fallback_ndvi(lat, lon)
    
    offset = 0.0005
    bbox = [lon - offset, lat - offset, lon + offset, lat + offset]
    
    payload = {
        "input": {
            "bounds": {"bbox": bbox},
            "data": [{
                "type": "sentinel-2-l2a",
                "dataFilter": {
                    "timeRange": {
                        "from": "2025-01-01T00:00:00Z",
                        "to": "2026-03-26T23:59:59Z"
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
            logger.warning("No data from Sentinel, using fallback")
            return _fallback_ndvi(lat, lon)
        
        avg_ndvi = data["data"][0]["outputs"]["default"]["bands"]["B0"]["stats"]["mean"]
        
        return {
            "status": "success",
            "ndvi": round(avg_ndvi, 3),
            "coordinates": {"lat": lat, "lon": lon},
            "source": "Sentinel-2 L2A via Sentinel Hub"
        }
    except requests.RequestException as e:
        logger.error(f"Sentinel Hub API error: {e}")
        return _fallback_ndvi(lat, lon)
    except (KeyError, IndexError, TypeError) as e:
        logger.error(f"Failed to parse response: {e}")
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


if __name__ == "__main__":
    print(get_real_ndvi(-33.125, -68.895))
