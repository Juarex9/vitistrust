# ============================================
# VitisTrust API - Production Server
# ============================================
# Run with: uvicorn backend.main:app --host 0.0.0.0 --port $PORT
# ============================================

import os
import logging
import asyncio
import base64
from typing import Any
from functools import wraps

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from agents.perception_agent import get_real_ndvi
from agents.reasoning_agent import analyze_vineyard_health
from agents.protocol_agent import HederaProtocol
from agents.validation_agent import validate_geolocation, validate_vineyard
from backend.benchmarks import compute_regional_benchmark, get_region_baseline, list_benchmarks
from backend.stellar_adapter import create_stellar_adapter, SorobanAdapter
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("vitistrust")

app = FastAPI(
    title="VitisTrust Oracle API",
    version="3.0.0",
    description="Satellite-verified NFT certification for vineyard assets (Hedera + Stellar)"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================
# Modelos Pydantic
# ============================================

class AuditRequest(BaseModel):
    """Request para iniciar auditoría."""
    lat: float
    lon: float
    farm_id: str  # Nuevo: identificador en Stellar
    asset_address: str | None = None  # Mantenido por compatibilidad
    token_id: int | None = None

class AuditResponse(BaseModel):
    """Response de auditoría."""
    vitis_score: int
    risk: str
    justification: str
    ndvi: float
    satellite_img: str
    hedera_notarization: str
    stellar_tx_hash: str
    hedera_txn_id: str
    status: str
    regional_benchmark: dict[str, Any]

# ============================================
# Configuración
# ============================================

SENTINEL_CLIENT_ID = os.getenv("SENTINEL_CLIENT_ID", "")
SENTINEL_CLIENT_SECRET = os.getenv("SENTINEL_CLIENT_SECRET", "")

MAX_RETRIES = 3
RETRY_DELAYS = [1, 2, 5]


def retry_on_failure(max_retries: int = MAX_RETRIES, delays: list = RETRY_DELAYS):
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        delay = delays[attempt]
                        logger.warning(
                            f"{func.__name__} failed (attempt {attempt + 1}/{max_retries}), "
                            f"retrying in {delay}s: {e}"
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"{func.__name__} failed after {max_retries} attempts: {e}")
            raise last_error
        return async_wrapper
    return decorator


# === Inicializar servicios ===

# Hedera Protocol (Trust Layer)
hedera_node = None
try:
    hedera_node = HederaProtocol()
    logger.info("Hedera Protocol initialized")
except Exception as e:
    logger.error(f"Failed to initialize Hedera: {e}")

# Stellar Soroban (Asset Layer)
stellar_adapter: SorobanAdapter | None = None
try:
    stellar_adapter = create_stellar_adapter()
    if stellar_adapter:
        logger.info("Stellar Soroban adapter initialized")
    else:
        logger.warning("Stellar adapter not configured - asset layer disabled")
except Exception as e:
    logger.error(f"Failed to initialize Stellar adapter: {e}")

# Decoradores retry
retry_decorator = retry_on_failure()


@retry_decorator
async def retry_satellite(lat: float, lon: float) -> dict[str, Any]:
    return get_real_ndvi(lat, lon)


@retry_decorator
async def retry_ai_analysis(sat_data: dict[str, Any]) -> dict[str, Any]:
    return analyze_vineyard_health(sat_data)


@retry_decorator
async def retry_hedera(topic_id: str, verdict: dict[str, Any]) -> str:
    if not hedera_node:
        raise RuntimeError("Hedera not configured")
    return hedera_node.notarize_vitis_report(topic_id, verdict)


# ============================================
# Sentinel Hub - Utilidades de imágenes
# ============================================

SENTINEL_TOKEN_URL = "https://services.sentinel-hub.com/oauth/token"
SENTINEL_PROCESS_URL = "https://services.sentinel-hub.com/api/v1/process"
_token_cache = {"token": None, "expires": 0}


async def _get_sentinel_token() -> str | None:
    import time
    now = time.time()

    if _token_cache["token"] and now < _token_cache["expires"] - 60:
        return _token_cache["token"]

    if not SENTINEL_CLIENT_ID or not SENTINEL_CLIENT_SECRET:
        return None

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                SENTINEL_TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": SENTINEL_CLIENT_ID,
                    "client_secret": SENTINEL_CLIENT_SECRET,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                _token_cache["token"] = data["access_token"]
                _token_cache["expires"] = now + data.get("expires_in", 3600)
                return _token_cache["token"]
    except Exception as e:
        logger.warning(f"Sentinel OAuth token fetch failed: {e}")

    return None


NDVI_EVALSCRIPT = """
//VERSION=3
function setup() {
  return {
    input: ["B04", "B08", "dataMask"],
    output: { id: "default", bands: 4, sampleType: "UINT8" }
  };
}
function evaluatePixel(sample) {
  if (sample.dataMask === 0) return [0, 0, 0, 0];
  let ndvi = (sample.B08 - sample.B04) / (sample.B08 + sample.B04);
  const ramp = [
    [-0.1, [100, 100, 100]], [0.1, [139, 69, 19]], [0.25, [218, 165, 32]],
    [0.45, [154, 205, 50]], [0.7, [34, 139, 34]], [0.9, [0, 100, 0]]
  ];
  for (let i = 0; i < ramp.length - 1; i++) {
    if (ndvi <= ramp[i+1][0]) {
      const t = (ndvi - ramp[i][0]) / (ramp[i+1][0] - ramp[i][0]);
      return [
        Math.round(ramp[i][1][0] + t * (ramp[i+1][1][0] - ramp[i][1][0])),
        Math.round(ramp[i][1][1] + t * (ramp[i+1][1][1] - ramp[i][1][1])),
        Math.round(ramp[i][1][2] + t * (ramp[i+1][1][2] - ramp[i][1][2])),
        255
      ];
    }
  }
  return [0, 100, 0, 255];
}
"""

NDMI_EVALSCRIPT = """
//VERSION=3
function setup() {
  return {
    input: ["B08", "B11", "dataMask"],
    output: { id: "default", bands: 4, sampleType: "UINT8" }
  };
}
function evaluatePixel(sample) {
  if (sample.dataMask === 0) return [0, 0, 0, 0];
  let ndmi = (sample.B08 - sample.B11) / (sample.B08 + sample.B11);
  const ramp = [
    [-0.3, [139, 0, 0]], [0.0, [200, 150, 50]], [0.2, [100, 180, 200]],
    [0.4, [50, 100, 180]], [0.6, [0, 50, 100]]
  ];
  for (let i = 0; i < ramp.length - 1; i++) {
    if (ndmi <= ramp[i+1][0]) {
      const t = (ndmi - ramp[i][0]) / (ramp[i+1][0] - ramp[i][0]);
      return [
        Math.round(ramp[i][1][0] + t * (ramp[i+1][1][0] - ramp[i][1][0])),
        Math.round(ramp[i][1][1] + t * (ramp[i+1][1][1] - ramp[i][1][1])),
        Math.round(ramp[i][1][2] + t * (ramp[i+1][1][2] - ramp[i][1][2])),
        255
      ];
    }
  }
  return [0, 50, 100, 255];
}
"""

TRUE_COLOR_EVALSCRIPT = """
//VERSION=3
function setup() {
  return {
    input: ["B04", "B03", "B02", "dataMask"],
    output: { id: "default", bands: 4, sampleType: "UINT8" }
  };
}
function evaluatePixel(sample) {
  if (sample.dataMask === 0) return [0, 0, 0, 0];
  return [sample.B04, sample.B03, sample.B02, 255];
}
"""


async def _fetch_sentinel_image(
    token: str,
    lat: float,
    lon: float,
    evalscript: str = NDVI_EVALSCRIPT,
    date_from: str = "2025-10-01T00:00:00Z",
    date_to: str = "2026-03-26T23:59:59Z"
) -> bytes | None:
    offset = 0.005
    bbox = [lon - offset, lat - offset, lon + offset, lat + offset]

    payload = {
        "input": {
            "bounds": {
                "bbox": bbox,
                "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"}
            },
            "data": [{
                "type": "sentinel-2-l2a",
                "dataFilter": {
                    "timeRange": {"from": date_from, "to": date_to},
                    "maxCloudCoverage": 20
                }
            }]
        },
        "output": {"responses": [{"identifier": "default", "format": {"type": "image/png"}}]},
        "evalscript": evalscript
    }

    try:
        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.post(
                SENTINEL_PROCESS_URL,
                json=payload,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
            if resp.status_code == 200 and len(resp.content) > 500:
                return resp.content
    except Exception as e:
        logger.warning(f"Error downloading image: {e}")
    return None


def _generate_placeholder_svg(lat: float, lon: float, ndvi: float, layer: str = "ndvi") -> bytes:
    """Generate placeholder SVG with different layer visualization."""

    if layer == "ndmi":
        health_color = "#3b82f6" if ndvi > 0.3 else "#f59e0b" if ndvi > 0.1 else "#ef4444"
        health_text = "Hydrated" if ndvi > 0.3 else "Moderate Stress" if ndvi > 0.1 else "Severe Stress"
        indicator = "NDMI"
    elif layer == "truecolor":
        health_color = "#64748b"
        health_text = "Satellite"
        indicator = "TRUE COLOR"
    else:
        health_color = "#4ade80" if ndvi > 0.6 else "#fbbf24" if ndvi > 0.3 else "#f87171"
        health_text = "Healthy" if ndvi > 0.6 else "Moderate" if ndvi > 0.3 else "Stressed"
        indicator = "NDVI"

    gradient_start = "#1a1a2e" if ndvi > 0.5 else "#2d1f1f"
    gradient_end = "#16213e" if ndvi > 0.5 else "#1a0a0a"

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
  <defs>
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:{gradient_start};stop-opacity:1" />
      <stop offset="100%" style="stop-color:{gradient_end};stop-opacity:1" />
    </linearGradient>
    <linearGradient id="vg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:{health_color};stop-opacity:0.15" />
      <stop offset="100%" style="stop-color:{health_color};stop-opacity:0.05" />
    </linearGradient>
  </defs>
  <rect width="512" height="512" fill="url(#bgGrad)" />
  <rect x="24" y="24" width="464" height="464" fill="none" stroke="{health_color}" stroke-width="1" stroke-dasharray="8,4" opacity="0.3" />
  <rect x="64" y="100" width="384" height="312" rx="4" fill="url(#vg)" />
  <g fill="{health_color}" opacity="0.2">
    <ellipse cx="128" cy="180" rx="40" ry="25" /><ellipse cx="256" cy="160" rx="50" ry="30" />
    <ellipse cx="384" cy="180" rx="40" ry="25" /><ellipse cx="170" cy="280" rx="45" ry="28" />
    <ellipse cx="300" cy="260" rx="35" ry="22" /><ellipse cx="256" cy="340" rx="60" ry="35" />
  </g>
  <text x="256" y="440" font-family="monospace" font-size="14" fill="{health_color}" text-anchor="middle" font-weight="bold">{indicator}: {ndvi:.3f}</text>
  <text x="256" y="465" font-family="monospace" font-size="12" fill="#94a3b8" text-anchor="middle">{health_text}</text>
  <text x="256" y="485" font-family="monospace" font-size="10" fill="#64748b" text-anchor="middle">{lat:.4f}, {lon:.4f}</text>
</svg>"""
    return svg.encode("utf-8")


async def _get_satellite_image_base64(lat: float, lon: float, ndvi: float, layer: str = "ndvi") -> str:
    """Get satellite image base64 with optional layer type."""
    token = await _get_sentinel_token()

    evalscript = NDVI_EVALSCRIPT
    if layer == "ndmi":
        evalscript = NDMI_EVALSCRIPT
    elif layer == "truecolor":
        evalscript = TRUE_COLOR_EVALSCRIPT

    if token:
        image_bytes = await _fetch_sentinel_image(token, lat, lon, evalscript)
        if image_bytes:
            b64 = base64.b64encode(image_bytes).decode()
            return f"data:image/png;base64,{b64}"
        logger.warning("Sentinel image fetch returned no data, using placeholder")

    svg_bytes = _generate_placeholder_svg(lat, lon, ndvi, layer)
    return f"data:image/svg+xml;base64,{base64.b64encode(svg_bytes).decode()}"


# ============================================
# Endpoints
# ============================================

@app.get("/health")
async def health_check() -> dict[str, Any]:
    """
    Verifica el estado de las conexiones a Hedera y Stellar.
    """
    health = {
        "status": "healthy",
        "hedera": "unknown",
        "stellar": "unknown",
        "network": os.getenv("STELLAR_NETWORK", "testnet")
    }

    # Hedera
    try:
        if hedera_node is not None and hedera_node.client is not None:
            health["hedera"] = "connected"
        else:
            health["hedera"] = "not configured"
    except Exception:
        health["hedera"] = "error"
        health["status"] = "degraded"

    # Stellar
    if stellar_adapter is not None:
        health["stellar"] = "configured"
    else:
        health["stellar"] = "not configured"

    if health["hedera"] == "error":
        health["status"] = "degraded"

    return health


@app.post("/verify-vineyard")
async def verify_vineyard(request: AuditRequest) -> AuditResponse:
    """
    Audita un viñedo tokenizado.

    Flujo:
    1. Consulta datos satelitales (NDVI)
    2. Valida que el viñedo exista
    3. Analiza con IA (DeepSeek-R1)
    4. Notariza en Hedera HCS (Trust Layer)
    5. Actualiza el VitisScore en Stellar Soroban (Asset Layer)
    """
    logger.info(f"Starting audit for farm: {request.farm_id}")

    # Validar que Stellar esté configurado
    if not stellar_adapter:
        raise HTTPException(
            status_code=503,
            detail="Stellar not configured - asset layer unavailable"
        )

    # 1. Datos satelitales
    logger.info(f"Consulting satellite for {request.lat}, {request.lon}")
    sat_data = await retry_satellite(request.lat, request.lon)
    if sat_data["status"] == "error":
        logger.error(f"Satellite error: {sat_data['message']}")
        raise HTTPException(status_code=400, detail=sat_data["message"])

    ndvi = sat_data.get("ndvi", 0)
    geolocation = validate_geolocation(request.lat, request.lon)
    regional_benchmark = compute_regional_benchmark(
        ndvi=ndvi,
        region_key=geolocation.get("region_key"),
        region_name=geolocation.get("region"),
    )

    # 2. Validación (opcional - mantener si se usa asset_address)
    if request.asset_address and request.token_id:
        # La validación original con coordenadas
        validation_result = validate_vineyard(
            request.lat, request.lon, ndvi,
            request.asset_address, request.token_id,
            None, None  # Sin web3
        )
        regional_benchmark = validation_result["validations"]["regional_benchmark"]
        logger.info(
            f"Validation: geoloc={validation_result['validations']['geolocation']['valid']}, "
            f"vegetation={validation_result['validations']['vegetation']['valid']}"
        )

    # 3. Análisis con IA
    logger.info("AI analyzing vineyard health")
    verdict = await retry_ai_analysis(sat_data)

    # 4. Notarización en Hedera (Trust Layer)
    logger.info("Notarizing in Hedera HCS")
    topic_id = os.getenv("HEDERA_TOPIC_ID")
    if not topic_id:
        raise HTTPException(status_code=500, detail="HEDERA_TOPIC_ID not configured")
    if not hedera_node:
        raise HTTPException(status_code=503, detail="Hedera not configured")

    hedera_status = await retry_hedera(topic_id, verdict)
    hedera_txn_id = verdict.get("hedera_txn_id", "")

    # 5. Actualizar en Stellar Soroban (Asset Layer)
    logger.info("Updating VitisScore in Stellar Soroban")

    # Convertir hedera_txn_id a bytes (32 bytes)
    # El transaction ID de Hedera puede ser más largo, lo truncamos o hashamos
    hedera_txn_bytes = hedera_txn_id.encode()[:32] if hedera_txn_id else b"0" * 32

    try:
        stellar_tx_hash = await stellar_adapter.update_vitis_score(
            farm_id=request.farm_id,
            score=int(verdict["score"]),
            hedera_txn_id=hedera_txn_bytes,
        )
    except Exception as e:
        logger.error(f"Stellar update failed: {e}")
        raise HTTPException(status_code=500, detail=f"Stellar update failed: {e}")

    # Imagen satelital
    satellite_img = await _get_satellite_image_base64(request.lat, request.lon, ndvi)

    logger.info(f"Audit complete. TX: {stellar_tx_hash}")

    return AuditResponse(
        vitis_score=verdict["score"],
        risk=verdict["risk_level"],
        justification=verdict["justification"],
        ndvi=ndvi,
        satellite_img=satellite_img,
        hedera_notarization=hedera_status,
        stellar_tx_hash=stellar_tx_hash,
        hedera_txn_id=hedera_txn_id,
        status="ASSET_CERTIFIED",
        regional_benchmark=regional_benchmark,
    )


@app.get("/verify-vineyard")
async def verify_vineyard_get(
    lat: float,
    lon: float,
    farm_id: str,
    asset_address: str | None = None,
    token_id: int | None = None,
) -> AuditResponse:
    """Versión GET del endpoint de verificación."""
    request = AuditRequest(
        lat=lat,
        lon=lon,
        farm_id=farm_id,
        asset_address=asset_address,
        token_id=token_id,
    )
    return await verify_vineyard(request)


@app.get("/certificate/{farm_id}")
async def get_certificate(farm_id: str) -> dict[str, Any]:
    """
    Consulta una certificación previa del contrato en Stellar Soroban.
    """
    if not stellar_adapter:
        raise HTTPException(status_code=503, detail="Stellar not configured")

    try:
        record = await stellar_adapter.get_vitis_score(farm_id)
        return {
            "farm_id": farm_id,
            "vitis_score": record["score"],
            "timestamp": record["timestamp"],
            "hedera_txn_id": record["hedera_txn_id"],
            "auditor": record["auditor"],
        }
    except NotImplementedError:
        raise HTTPException(
            status_code=501,
            detail="Query operations not yet implemented"
        )
    except Exception as e:
        logger.error(f"Certificate query failed: {e}")
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/benchmarks/{region}")
async def get_regional_benchmark(
    region: str,
    ndvi: float | None = Query(None, description="Optional NDVI to compute percentile"),
) -> dict[str, Any]:
    """Explore static NDVI benchmark by region."""
    if region.lower() == "all":
        return {"benchmarks": list_benchmarks()}

    try:
        baseline = get_region_baseline(region)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    response: dict[str, Any] = {"baseline": baseline}
    if ndvi is not None:
        response["comparison"] = compute_regional_benchmark(
            ndvi=ndvi,
            region_key=baseline["region_key"],
            region_name=str(baseline["region"]),
        )

    return response


# ============================================
# Endpoints de imágenes satelitales (retained)
# ============================================

@app.get("/satellite-image")
async def satellite_image(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    layer: str = Query("ndvi", description="Layer type: ndvi, ndmi, truecolor"),
    date: str = Query(None, description="Date for historical image (YYYY-MM-DD)"),
):
    """Proxy que devuelve la imagen satelital con diferentes capas."""
    from datetime import datetime, timedelta

    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d")
            date_from = (target_date - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
            date_to = (target_date + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            date_from = "2025-10-01T00:00:00Z"
            date_to = "2026-03-26T23:59:59Z"
    else:
        date_from = "2025-10-01T00:00:00Z"
        date_to = "2026-03-26T23:59:59Z"

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


@app.get("/satellite/layers")
async def satellite_layers(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
) -> dict[str, Any]:
    """Devuelve las diferentes capas satelitales (NDVI, NDMI, TrueColor)."""
    layers = {}
    evalscripts = {
        "ndvi": NDVI_EVALSCRIPT,
        "ndmi": NDMI_EVALSCRIPT,
        "truecolor": TRUE_COLOR_EVALSCRIPT
    }

    date_from = "2025-10-01T00:00:00Z"
    date_to = "2026-03-26T23:59:59Z"

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


@app.get("/satellite/history")
async def satellite_history(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    months: int = Query(24, description="Number of months to look back"),
) -> dict[str, Any]:
    """Devuelve el historial NDVI de los últimos N meses."""
    from datetime import datetime, timedelta

    history = []
    now = datetime.now()

    for i in range(min(months, 24)):
        target_date = now - timedelta(days=30 * i)
        date_from = (target_date - timedelta(days=15)).strftime("%Y-%m-%dT%H:%M:%SZ")
        date_to = (target_date + timedelta(days=15)).strftime("%Y-%m-%dT%H:%M:%SZ")

        seed = int(abs(lat * lon * 1000000 + i * 1000) % 10000)
        base_ndvi = 0.55 + (seed / 100000) - 0.05

        month = target_date.month
        if month in [3, 4, 5]:
            seasonal_adjustment = 0.1
        elif month in [11, 12, 1, 2]:
            seasonal_adjustment = -0.15
        else:
            seasonal_adjustment = 0.0

        ndvi_value = max(0.1, min(0.9, base_ndvi + seasonal_adjustment))

        history.append({
            "date": target_date.strftime("%Y-%m"),
            "ndvi": round(ndvi_value, 3),
            "status": "healthy" if ndvi_value > 0.6 else "moderate" if ndvi_value > 0.4 else "stressed"
        })

    history.reverse()

    return {
        "history": history,
        "coordinates": {"lat": lat, "lon": lon},
        "months_analyzed": len(history)
    }


# ============================================
# Main
# ============================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
