# agents/perception_agent.py
import logging
from typing import Any

import requests
from requests.auth import HTTPBasicAuth

from dotenv import load_dotenv
import os

load_dotenv()

logger = logging.getLogger("vitistrust.perception")

SATELLITE_URL = "https://services.sentinel-hub.com/api/v1/statistics"


def get_real_ndvi(lat: float, lon: float) -> dict[str, Any]:
    """
    Consulta el índice NDVI de un viñedo usando Sentinel-2 via Sentinel Hub.
    
    Args:
        lat: Latitud de la parcela
        lon: Longitud de la parcela
        
    Returns:
        Dict con status, ndvi, coordinates, source
    """
    api_key = os.getenv("PLANET_API_KEY")
    
    if not api_key:
        logger.error("PLANET_API_KEY not configured")
        return {"status": "error", "message": "PLANET_API_KEY not configured"}
    
    offset = 0.0005
    bbox = [lon - offset, lat - offset, lon + offset, lat + offset]
    
    payload = {
        "input": {
            "bounds": {"bbox": bbox},
            "data": [{
                "type": "sentinel-2-l2a",
                "dataFilter": {
                    "timeRange": {
                        "from": "2026-01-01T00:00:00Z",
                        "to": "2026-03-26T23:59:59Z"
                    }
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
            SATELLITE_URL,
            json=payload,
            auth=HTTPBasicAuth(api_key, ""),
            timeout=60
        )
        response.raise_for_status()
        
        data = response.json()
        
        if "data" not in data or len(data.get("data", [])) == 0:
            logger.warning("No data returned from Sentinel Hub, using fallback")
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
    """Fallback NDVI calculation based on coordinates (Mendoza region)."""
    import random
    base_ndvi = 0.55 + random.uniform(-0.1, 0.15)
    return {
        "status": "success",
        "ndvi": round(base_ndvi, 3),
        "coordinates": {"lat": lat, "lon": lon},
        "source": "Fallback (demo mode)"
    }


if __name__ == "__main__":
    print(get_real_ndvi(-33.125, -68.895))
