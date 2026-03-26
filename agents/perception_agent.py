# agents/perception_agent.py
import logging
import os
import time
from typing import Any

import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth

load_dotenv()

logger = logging.getLogger("vitistrust.perception")

# Simple Cache for the Hackathon Demo
QUERY_CACHE: dict[str, dict[str, Any]] = {}

def get_real_ndvi(lat: float, lon: float) -> dict[str, Any]:
    """
    Fetch satellite data and mock weather context.
    Includes caching and deterministic demo fallback.
    """
    # 1. Check Cache
    cache_key = f"{round(lat, 4)}_{round(lon, 4)}"
    if cache_key in QUERY_CACHE:
        logger.info(f"Returning cached data for {cache_key}")
        return QUERY_CACHE[cache_key]

    # 2. Deterministic Demo Logic: Mendoza North vs South
    # North (e.g., > -33.0) -> Healthy
    # South (e.g., < -33.0) -> Drought/Stressed
    is_mendoza = -34.0 < lat < -32.0 and -69.5 < lon < -67.5
    
    # Try real API if key is present, otherwise fallback (deterministic)
    api_key = os.getenv("PLANET_API_KEY")
    if api_key and not is_mendoza:
        # Real logic would be here (omitted for brevity in demo context)
        # We'll use the fallback for the "controlled pitch" anyway
        result = _fallback_ndvi(lat, lon)
    else:
        result = _fallback_ndvi(lat, lon)

    # 3. Add Simulated Weather Context for credibility
    if is_mendoza and lat < -33.0:
        # Southern Mendoza - Heavy Drought Simulation
        result["weather_context"] = {
            "temperature_celsius": 36.2,
            "humidity_percent": 11.5,
            "precipitation_last_7_days_mm": 0.0,
            "weather_warning": "Severe Drought Alert"
        }
    else:
        # Northern Mendoza or Other - Ideal conditions
        result["weather_context"] = {
            "temperature_celsius": 24.5,
            "humidity_percent": 42.0,
            "precipitation_last_7_days_mm": 4.5,
            "weather_warning": "Normal"
        }

    # 4. Generate "Eye Candy" Satellite Image (Base64 placeholder)
    result["satellite_img"] = _generate_mock_satellite_img(result["ndvi"])

    # 5. Cache and return
    QUERY_CACHE[cache_key] = result
    return result


def _generate_mock_satellite_img(ndvi: float) -> str:
    """Returns a placeholder image URL based on NDVI for UI rendering."""
    # In a real scenario, this would be a base64 encoded string from Sentinel Hub
    color = "228B22" if ndvi > 0.6 else "DAA520" if ndvi > 0.3 else "8B4513"
    return f"https://placehold.co/600x400/{color}/ffffff?text=NDVI+Analysis:+{ndvi}"


def _fallback_ndvi(lat: float, lon: float) -> dict[str, Any]:
    """Deterministic values for the interactive hackathon pitch."""
    # North Mendoza -> Excellent
    if lat > -33.0:
        ndvi = 0.785
        status = "Healthy"
    # South Mendoza -> Poor
    else:
        ndvi = 0.282
        status = "Stressed"
        
    return {
        "status": "success",
        "ndvi": ndvi,
        "coordinates": {"lat": lat, "lon": lon},
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "Sentinel-2 (Deterministic Demo Mode)"
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(get_real_ndvi(-33.125, -68.895))
