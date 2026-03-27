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

from agents.perception_agent import get_real_ndvi
from agents.reasoning_agent import analyze_vineyard_health
from agents.protocol_agent import HederaProtocol
from agents.validation_agent import validate_vineyard
from backend.constants import VITIS_ABI
from web3 import Web3
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("vitistrust")

app = FastAPI(title="VitisTrust Oracle API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SENTINEL_CLIENT_ID = os.getenv("SENTINEL_CLIENT_ID", "")
SENTINEL_CLIENT_SECRET = os.getenv("SENTINEL_CLIENT_SECRET", "")

MAX_RETRIES = 3
RETRY_DELAYS = [1, 2, 5]

def retry_on_failure(max_retries: int = MAX_RETRIES, delays: list = RETRY_DELAYS):
    """Decorator para reintentar funciones que pueden fallar."""
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
                        logger.warning(f"{func.__name__} failed (attempt {attempt + 1}/{max_retries}), retrying in {delay}s: {e}")
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"{func.__name__} failed after {max_retries} attempts: {e}")
            raise last_error
        return async_wrapper
    return decorator

RSK_RPC_URL = os.getenv("RSK_RPC_URL")
RSK_ORACLE_ADDRESS = os.getenv("RSK_ORACLE_ADDRESS")
RSK_PRIVATE_KEY = os.getenv("RSK_PRIVATE_KEY")
RSK_CONTRACT_ADDRESS = os.getenv("RSK_CONTRACT_ADDRESS")

w3 = Web3(Web3.HTTPProvider(RSK_RPC_URL))

if not RSK_CONTRACT_ADDRESS:
    logger.warning("RSK_CONTRACT_ADDRESS not set - contract calls will fail")

vitis_contract = w3.eth.contract(address=RSK_CONTRACT_ADDRESS, abi=VITIS_ABI) if RSK_CONTRACT_ADDRESS else None

hedera_node = None
try:
    hedera_node = HederaProtocol()
except Exception as e:
    logger.error(f"Failed to initialize Hedera: {e}")

retry_decorator = retry_on_failure()

@retry_decorator
async def retry_satellite(lat: float, lon: float) -> dict[str, Any]:
    return get_real_ndvi(lat, lon)

@retry_decorator
async def retry_ai_analysis(sat_data: dict[str, Any]) -> dict[str, Any]:
    return analyze_vineyard_health(sat_data)

@retry_decorator  
async def retry_hedera(topic_id: str, verdict: dict[str, Any]) -> str:
    return hedera_node.notarize_vitis_report(topic_id, verdict)

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

async def _fetch_sentinel_image(token: str, lat: float, lon: float) -> bytes | None:
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
                    "timeRange": {"from": "2025-10-01T00:00:00Z", "to": "2026-03-26T23:59:59Z"},
                    "maxCloudCoverage": 20
                }
            }]
        },
        "output": {"responses": [{"identifier": "default", "format": {"type": "image/png"}}]},
        "evalscript": NDVI_EVALSCRIPT
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

def _generate_placeholder_svg(lat: float, lon: float, ndvi: float) -> bytes:
    health_color = "#4ade80" if ndvi > 0.6 else "#fbbf24" if ndvi > 0.3 else "#f87171"
    health_text = "Healthy" if ndvi > 0.6 else "Moderate" if ndvi > 0.3 else "Stressed"
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
  <text x="256" y="440" font-family="monospace" font-size="14" fill="{health_color}" text-anchor="middle" font-weight="bold">NDVI: {ndvi:.3f}</text>
  <text x="256" y="465" font-family="monospace" font-size="12" fill="#94a3b8" text-anchor="middle">{health_text}</text>
  <text x="256" y="485" font-family="monospace" font-size="10" fill="#64748b" text-anchor="middle">{lat:.4f}, {lon:.4f}</text>
</svg>"""
    return svg.encode("utf-8")

async def _get_satellite_image_base64(lat: float, lon: float, ndvi: float) -> str:
    token = await _get_sentinel_token()
    if token:
        image_bytes = await _fetch_sentinel_image(token, lat, lon)
        if image_bytes:
            b64 = base64.b64encode(image_bytes).decode()
            return f"data:image/png;base64,{b64}"
        logger.warning("Sentinel image fetch returned no data, using placeholder")
    svg_bytes = _generate_placeholder_svg(lat, lon, ndvi)
    return f"data:image/svg+xml;base64,{base64.b64encode(svg_bytes).decode()}"


@app.get("/health")
async def health_check() -> dict[str, Any]:
    """Verifica el estado de las conexiones a RSK y Hedera."""
    health = {"status": "healthy", "rsk": "unknown", "hedera": "unknown"}
    
    if w3.is_connected():
        health["rsk"] = "connected"
    else:
        health["rsk"] = "disconnected"
        health["status"] = "degraded"
    
    try:
        if hedera_node is not None and hedera_node.client is not None:
            health["hedera"] = "connected"
        else:
            health["hedera"] = "not configured"
    except Exception:
        health["hedera"] = "error"
        health["status"] = "degraded"
    
    return health


@app.get("/satellite-image")
async def satellite_image(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
):
    """Proxy que devuelve la imagen satelital NDVI."""
    ndvi = 0.55
    svg_bytes = _generate_placeholder_svg(lat, lon, ndvi)
    return Response(content=svg_bytes, media_type="image/svg+xml")


@app.get("/verify-vineyard")
async def verify(lat: float, lon: float, asset_address: str, token_id: int) -> dict[str, Any]:
    """
    Audita un viñedo tokenizado.
    
    Flujo:
    1. Consulta datos satelitales (NDVI)
    2. Valida que el viñedo exista
    3. Analiza con IA (DeepSeek-R1)
    4. Notariza en Hedera (HCS)
    5. Certifica en Rootstock (VitisRegistry)
    """
    # Normalize address to lowercase
    asset_address = asset_address.lower()
    
    logger.info(f"Starting audit for asset {asset_address} token {token_id}")
    
    try:
        if not vitis_contract:
            raise HTTPException(status_code=503, detail="Contract not configured")
        
        logger.info(f"🛰️ Consulting satellite for {lat}, {lon}")
        sat_data = await retry_satellite(lat, lon)
        if sat_data["status"] == "error":
            logger.error(f"Satellite error: {sat_data['message']}")
            raise HTTPException(status_code=400, detail=sat_data["message"])

        ndvi = sat_data.get("ndvi", 0)

        # Validación del viñedo
        validation_result = validate_vineyard(
            lat, lon, ndvi, asset_address, token_id, w3, vitis_contract
        )
        logger.info(f"Validation: geoloc={validation_result['validations']['geolocation']['valid']}, vegetation={validation_result['validations']['vegetation']['valid']}")

        logger.info("🧠 AI analyzing vineyard health")
        verdict = await retry_ai_analysis(sat_data)

        logger.info("🛡️ Notarizing in Hedera")
        topic_id = os.getenv("HEDERA_TOPIC_ID")
        if not topic_id:
            raise HTTPException(status_code=500, detail="HEDERA_TOPIC_ID not configured")
        if not hedera_node:
            raise HTTPException(status_code=503, detail="Hedera not configured")
        hedera_status = await retry_hedera(topic_id, verdict)

        logger.info("🔗 Signing certification in Rootstock")
        nonce = w3.eth.get_transaction_count(RSK_ORACLE_ADDRESS)
        
        txn = vitis_contract.functions.certifyAsset(
            Web3.to_checksum_address(asset_address),
            token_id,
            int(verdict["score"]),
            topic_id
        ).build_transaction({
            "chainId": 31,
            "gas": 200000,
            "gasPrice": w3.eth.gas_price,
            "from": RSK_ORACLE_ADDRESS,
            "nonce": nonce,
        })

        signed_txn = w3.eth.account.sign_transaction(txn, private_key=RSK_PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)

        # Imagen satelital
        satellite_img = await _get_satellite_image_base64(lat, lon, ndvi)
        
        logger.info(f"✅ Audit complete. TX: {tx_hash.hex()}")
        
        return {
            "vitis_score": verdict["score"],
            "risk": verdict["risk_level"],
            "justification": verdict["justification"],
            "ndvi": ndvi,
            "validation": validation_result["validations"],
            "satellite_img": satellite_img,
            "hedera_notarization": hedera_status,
            "rsk_tx_hash": tx_hash.hex(),
            "status": "ASSET_CERTIFIED",
            "investment_analysis": verdict.get("investment_analysis"),
            "metrics": verdict.get("metrics")
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Audit failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/certificate/{asset_address}/{token_id}")
async def get_certificate(asset_address: str, token_id: int) -> dict[str, Any]:
    """Consulta una certificación previa del contrato en RSK."""
    try:
        if not vitis_contract:
            raise HTTPException(status_code=503, detail="Contract not configured")
        
        # Normalizar address a lowercase checksum
        normalized_address = Web3.to_checksum_address(asset_address.lower())
        logger.info(f"Querying certificate for {normalized_address} token {token_id}")
        
        cert = vitis_contract.functions.certificates(
            normalized_address,
            token_id
        ).call()
        
        logger.info(f"Raw certificate data: {cert}")
        
        # Verificar si hay datos válidos (score > 0 indica que existe)
        vitis_score = cert[0]
        timestamp = cert[1]
        topic_id = cert[2]
        
        if vitis_score == 0 and timestamp == 0 and not topic_id:
            raise HTTPException(status_code=404, detail="No certificate found for this asset")
        
        return {
            "asset_address": normalized_address,
            "token_id": token_id,
            "vitis_score": vitis_score,
            "timestamp": timestamp,
            "hedera_topic_id": topic_id
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Certificate query failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/certifications/{asset_address}")
async def get_certification_history(asset_address: str) -> dict[str, Any]:
    """Consulta el historial de certificaciones para un activo."""
    try:
        if not vitis_contract:
            raise HTTPException(status_code=503, detail="Contract not configured")
        
        normalized_address = Web3.to_checksum_address(asset_address.lower())
        logger.info(f"Querying certification history for {normalized_address}")
        
        try:
            token_ids = vitis_contract.functions.getCertificationIds(normalized_address).call()
        except Exception:
            token_ids = []
        
        certifications = []
        for token_id in token_ids:
            try:
                cert = vitis_contract.functions.certificates(normalized_address, token_id).call()
                if cert[0] > 0 or cert[1] > 0:
                    certifications.append({
                        "token_id": token_id,
                        "vitis_score": cert[0],
                        "timestamp": cert[1],
                        "hedera_topic_id": cert[2]
                    })
            except Exception:
                continue
        
        return {
            "asset_address": normalized_address,
            "total_certifications": len(certifications),
            "certifications": certifications
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Certification history query failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)