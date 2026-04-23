# ============================================
# VitisTrust API - Production Server
# ============================================
# Run with: uvicorn backend.main:app --host 0.0.0.0 --port $PORT
# ============================================

import os
import logging
import asyncio
import inspect
import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone, UTC
from pathlib import Path
import statistics
import time
from typing import Any
from dataclasses import dataclass
from functools import wraps

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from agents.perception_agent import get_real_indices, get_water_stress_level, get_real_ndvi
from agents.reasoning_agent import analyze_vineyard_health, SCORE_MODEL_VERSION
from agents.protocol_agent import HederaProtocol
from agents.validation_agent import validate_geolocation, validate_vineyard, validate_vegetation
from backend.benchmarks import compute_regional_benchmark, list_benchmarks
from backend.stellar_adapter import create_stellar_adapter, SorobanAdapter
from backend.time_window import build_time_window, format_iso_utc, parse_iso_datetime
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

class AlertEvidence(BaseModel):
    """Evidencia cuantitativa de la alerta."""
    current_ndvi: float
    baseline_ndvi: float | None = None
    change: float | None = None
    moving_avg_3m: float | None = None


class AlertItem(BaseModel):
    """Alerta de salud del viñedo."""
    rule_id: str
    severity: str
    title: str
    probable_cause: str
    triggered_at: str
    evidence: AlertEvidence

class AuditResponse(BaseModel):
    """Response de auditoría."""
    vitis_score: int
    risk: str
    justification: str
    ndvi: float
    ndmi: float
    water_stress_level: str
    satellite_img: str
    hedera_notarization: str
    stellar_tx_hash: str
    hedera_txn_id: str
    evidence_cid: str
    score_model_version: str
    score_breakdown: dict[str, Any]
    status: str
    alerts: list[AlertItem] = Field(default_factory=list)
    regional_benchmark: dict[str, Any]
    investment_analysis: dict[str, Any] | None = None
    validation: dict[str, Any] | None = None
    lat: float | None = None
    lon: float | None = None
    source: str | None = None


class OpenDisputeRequest(BaseModel):
    record_id: str
    bond: float
    reason: str | None = None
    challenger: str


class ResolveDisputeRequest(BaseModel):
    record_id: str
    verdict: bool
    resolver: str
    notes: str | None = None


class UpdateScoringModelRequest(BaseModel):
    version: int
    updated_by: str
    changelog: str | None = None


class DisputeResponse(BaseModel):
    record_id: str
    status: str
    bond: float
    scoring_model_version: int
    challenger: str
    resolver: str | None = None
    verdict: bool | None = None
    hedera_status: str | None = None
    hedera_txn_id: str | None = None
    created_at: str
    resolved_at: str | None = None

# ============================================
# Configuración
# ============================================

SENTINEL_CLIENT_ID = os.getenv("SENTINEL_CLIENT_ID", "")
SENTINEL_CLIENT_SECRET = os.getenv("SENTINEL_CLIENT_SECRET", "")

MAX_RETRIES = 3
RETRY_DELAYS = [1, 2, 5]
DEFAULT_SERVICE_TIMEOUTS = {
    "satellite": float(os.getenv("SATELLITE_TIMEOUT_S", "25")),
    "ai": float(os.getenv("AI_TIMEOUT_S", "35")),
    "hedera": float(os.getenv("HEDERA_TIMEOUT_S", "20")),
    "stellar": float(os.getenv("STELLAR_TIMEOUT_S", "60")),
}


@dataclass
class CircuitBreaker:
    name: str
    failure_threshold: int = 3
    recovery_timeout_s: float = 60.0
    failure_count: int = 0
    opened_at: float = 0.0
    state: str = "closed"

    def allow_request(self) -> bool:
        if self.state == "open":
            if time.monotonic() - self.opened_at >= self.recovery_timeout_s:
                self.state = "half_open"
                return True
            return False
        return True

    def record_success(self) -> None:
        self.failure_count = 0
        self.state = "closed"
        self.opened_at = 0.0

    def record_failure(self) -> None:
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold:
            self.state = "open"
            self.opened_at = time.monotonic()
            logger.warning(f"Circuit breaker opened for {self.name}")

    def snapshot(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout_s": self.recovery_timeout_s,
        }


SERVICE_BREAKERS: dict[str, CircuitBreaker] = {
    "satellite": CircuitBreaker("satellite"),
    "ai": CircuitBreaker("ai"),
    "hedera": CircuitBreaker("hedera"),
    "stellar": CircuitBreaker("stellar"),
}

LATEST_STAGE_METRICS: dict[str, float] = {
    "satellite_ms": 0.0,
    "ai_ms": 0.0,
    "hedera_ms": 0.0,
    "stellar_ms": 0.0,
}
ALERT_HISTORY: dict[str, list[dict[str, Any]]] = {}
MIN_DISPUTE_BOND = float(os.getenv("MIN_DISPUTE_BOND", "0.01"))
INITIAL_ARBITRATOR = os.getenv("INITIAL_ARBITRATOR", "INV_ADMIN_MULTISIG")

_disputes: dict[str, dict[str, Any]] = {}
_disputes_lock = asyncio.Lock()
_current_scoring_model_version = int(os.getenv("SCORING_MODEL_VERSION", "1"))


def retry_on_failure(max_retries: int = MAX_RETRIES, delays: list = RETRY_DELAYS):
    def decorator(func):
        def _log_retry(attempt: int, error: Exception):
            delay = delays[attempt]
            logger.warning(
                f"{func.__name__} failed (attempt {attempt + 1}/{max_retries}), "
                f"retrying in {delay}s: {error}"
            )
            return delay

        def _log_failure(error: Exception):
            logger.error(f"{func.__name__} failed after {max_retries} attempts: {error}")

        if inspect.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                last_error = None
                for attempt in range(max_retries):
                    try:
                        return await func(*args, **kwargs)
                    except Exception as e:
                        last_error = e
                        if attempt < max_retries - 1:
                            delay = _log_retry(attempt, e)
                            await asyncio.sleep(delay)
                        else:
                            _log_failure(e)
                raise last_error

            return async_wrapper

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        delay = _log_retry(attempt, e)
                        time.sleep(delay)
                    else:
                        _log_failure(e)
            raise last_error

        return sync_wrapper

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
    return get_real_indices(lat, lon)


@retry_decorator
async def retry_ai_analysis(sat_data: dict[str, Any]) -> dict[str, Any]:
    return analyze_vineyard_health(sat_data)


@retry_decorator
async def retry_hedera(topic_id: str, verdict: dict[str, Any]) -> dict[str, str]:
    if not hedera_node:
        raise RuntimeError("Hedera not configured")
    return hedera_node.notarize_vitis_report(topic_id, verdict)


async def _execute_with_timeout_and_breaker(
    service_name: str,
    operation_coro: Any,
) -> Any:
    breaker = SERVICE_BREAKERS[service_name]
    if not breaker.allow_request():
        raise RuntimeError(f"{service_name} service temporarily unavailable (circuit breaker open)")

    timeout_s = DEFAULT_SERVICE_TIMEOUTS[service_name]
    try:
        result = await asyncio.wait_for(operation_coro, timeout=timeout_s)
        breaker.record_success()
        return result
    except asyncio.TimeoutError as exc:
        breaker.record_failure()
        raise RuntimeError(f"{service_name} timeout after {timeout_s}s") from exc
    except Exception:
        breaker.record_failure()
        raise
async def _notarize_dispute_payload(payload: dict[str, Any]) -> tuple[str, str]:
    topic_id = os.getenv("HEDERA_TOPIC_ID")
    if not topic_id:
        return ("HEDERA_TOPIC_NOT_CONFIGURED", "")
    if not hedera_node:
        return ("HEDERA_NOT_CONFIGURED", "")

    status = await retry_hedera(topic_id, payload)
    return (status, payload.get("hedera_txn_id", ""))


# ============================================
# Sentinel Hub - Utilidades de imágenes
# ============================================

SENTINEL_TOKEN_URL = "https://services.sentinel-hub.com/oauth/token"
SENTINEL_PROCESS_URL = "https://services.sentinel-hub.com/api/v1/process"
_token_cache = {"token": None, "expires": 0}
EVIDENCE_INDEX_PATH = Path("backend/data/evidence_index.json")


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
    date_from: str | None = None,
    date_to: str | None = None
) -> bytes | None:
    offset = 0.005
    bbox = [lon - offset, lat - offset, lon + offset, lat + offset]

    requested_from, requested_to = (
        (date_from, date_to) if date_from and date_to else build_time_window(180)
    )
    fallback_from, fallback_to = build_time_window(365)
    windows: list[tuple[str, str, str]] = [
        (requested_from, requested_to, "requested"),
        (fallback_from, fallback_to, "fallback-expanded"),
    ]

    try:
        async with httpx.AsyncClient(timeout=45) as client:
            for current_from, current_to, window_label in windows:
                logger.info(
                    "Satellite image query window=%s from=%s to=%s lat=%s lon=%s",
                    window_label,
                    current_from,
                    current_to,
                    lat,
                    lon,
                )

                payload = {
                    "input": {
                        "bounds": {
                            "bbox": bbox,
                            "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"}
                        },
                        "data": [{
                            "type": "sentinel-2-l2a",
                            "dataFilter": {
                                "timeRange": {"from": current_from, "to": current_to},
                                "maxCloudCoverage": 20
                            }
                        }]
                    },
                    "output": {"responses": [{"identifier": "default", "format": {"type": "image/png"}}]},
                    "evalscript": evalscript
                }

                resp = await client.post(
                    SENTINEL_PROCESS_URL,
                    json=payload,
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                )
                if resp.status_code == 200 and len(resp.content) > 500:
                    return resp.content
                logger.warning(
                    "Sentinel image empty for window=%s from=%s to=%s status=%s size=%s",
                    window_label,
                    current_from,
                    current_to,
                    resp.status_code,
                    len(resp.content),
                )
    except Exception as e:
        logger.warning(f"Error downloading image: {e}")
    return None


def _resolve_window(
    date: str | None = None,
    from_param: str | None = None,
    to_param: str | None = None,
) -> tuple[str, str]:
    if from_param or to_param:
        if not from_param or not to_param:
            raise HTTPException(
                status_code=422,
                detail="Both 'from' and 'to' query params are required when overriding time window",
            )
        try:
            parsed_from = parse_iso_datetime(from_param)
            parsed_to = parse_iso_datetime(to_param)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid ISO datetime format for 'from'/'to': {exc}",
            ) from exc

        if parsed_from >= parsed_to:
            raise HTTPException(
                status_code=422,
                detail="'from' must be earlier than 'to'",
            )
        return format_iso_utc(parsed_from), format_iso_utc(parsed_to)

    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC)
            return build_time_window(days_back=60, end=target_date + timedelta(days=30))
        except ValueError:
            logger.warning("Invalid date format for /satellite-image date=%s, using default window", date)

    return build_time_window(180)


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


def _decode_data_uri_image(data_uri: str) -> tuple[bytes, str]:
    header, encoded = data_uri.split(",", 1)
    mime_type = header.split(";")[0].replace("data:", "")
    return base64.b64decode(encoded), mime_type


def _read_evidence_index() -> dict[str, Any]:
    if not EVIDENCE_INDEX_PATH.exists():
        return {}
    return json.loads(EVIDENCE_INDEX_PATH.read_text(encoding="utf-8"))


def _write_evidence_index(index_data: dict[str, Any]) -> None:
    EVIDENCE_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_INDEX_PATH.write_text(
        json.dumps(index_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _compute_file_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _build_evidence_payload(
    farm_id: str,
    lat: float,
    lon: float,
    ndvi: float,
    ndmi: float,
    justification: str,
    processed_image_bytes: bytes,
    processed_image_mime: str,
) -> dict[str, Any]:
    timestamp = datetime.now(tz=timezone.utc).isoformat()
    image_hash = _compute_file_sha256(processed_image_bytes)
    return {
        "farm_id": farm_id,
        "coordinates": {"lat": lat, "lon": lon},
        "indices": {"ndvi": ndvi, "ndmi": ndmi},
        "ai_justification": justification,
        "processed_image": {
            "mime_type": processed_image_mime,
            "sha256": image_hash,
        },
        "hashes": {
            "payload_sha256": _compute_file_sha256(
                json.dumps(
                    {
                        "farm_id": farm_id,
                        "coordinates": {"lat": lat, "lon": lon},
                        "indices": {"ndvi": ndvi, "ndmi": ndmi},
                        "ai_justification": justification,
                        "processed_image_sha256": image_hash,
                    },
                    sort_keys=True,
                    ensure_ascii=False,
                ).encode("utf-8")
            )
        },
        "timestamp": timestamp,
    }


async def _upload_evidence_to_ipfs(
    evidence_payload: dict[str, Any],
    processed_image_bytes: bytes,
    image_mime_type: str,
) -> dict[str, str]:
    provider_url = os.getenv("PINNING_PROVIDER_URL")
    provider_token = os.getenv("PINNING_PROVIDER_TOKEN", "")
    gateway_base = os.getenv("IPFS_GATEWAY_BASE", "https://ipfs.io/ipfs")

    if not provider_url:
        logger.warning("PINNING_PROVIDER_URL missing, using deterministic mock CID")
        digest = _compute_file_sha256(json.dumps(evidence_payload, sort_keys=True).encode("utf-8"))
        mock_cid = f"mockcid-{digest[:46]}"
        return {
            "evidence_cid": mock_cid,
            "evidence_json_cid": mock_cid,
            "image_cid": f"mockimg-{digest[:46]}",
            "gateway_url": f"{gateway_base}/{mock_cid}",
            "provider": "mock",
        }

    headers: dict[str, str] = {}
    if provider_token:
        headers["Authorization"] = f"Bearer {provider_token}"

    files = {
        "file": ("evidence.json", json.dumps(evidence_payload, indent=2).encode("utf-8"), "application/json")
    }
    async with httpx.AsyncClient(timeout=60) as client:
        json_resp = await client.post(provider_url, files=files, headers=headers)
        json_resp.raise_for_status()
        evidence_json_cid = json_resp.json().get("cid") or json_resp.json().get("IpfsHash")

        image_files = {
            "file": ("processed_image", processed_image_bytes, image_mime_type)
        }
        image_resp = await client.post(provider_url, files=image_files, headers=headers)
        image_resp.raise_for_status()
        image_cid = image_resp.json().get("cid") or image_resp.json().get("IpfsHash")

    if not evidence_json_cid or not image_cid:
        raise RuntimeError("Pinning provider did not return CID")

    return {
        "evidence_cid": evidence_json_cid,
        "evidence_json_cid": evidence_json_cid,
        "image_cid": image_cid,
        "gateway_url": f"{gateway_base}/{evidence_json_cid}",
        "provider": provider_url,
    }




def _build_history_point(lat: float, lon: float, offset_months: int, now: datetime) -> dict[str, Any]:
    target_date = now - timedelta(days=30 * offset_months)
    seed = int(abs(lat * lon * 1000000 + offset_months * 1000) % 10000)
    base_ndvi = 0.55 + (seed / 100000) - 0.05

    month = target_date.month
    if month in [3, 4, 5]:
        seasonal_adjustment = 0.1
    elif month in [11, 12, 1, 2]:
        seasonal_adjustment = -0.15
    else:
        seasonal_adjustment = 0.0

    ndvi_value = max(0.1, min(0.9, base_ndvi + seasonal_adjustment))
    return {
        "date": target_date.strftime("%Y-%m"),
        "ndvi": round(ndvi_value, 3),
        "status": "healthy" if ndvi_value > 0.6 else "moderate" if ndvi_value > 0.4 else "stressed",
    }


def _enrich_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for idx, point in enumerate(history):
        if idx == 0:
            point["monthly_change"] = None
        else:
            point["monthly_change"] = round(point["ndvi"] - history[idx - 1]["ndvi"], 3)

        window = history[max(0, idx - 2): idx + 1]
        point["moving_avg_3m"] = round(sum(item["ndvi"] for item in window) / len(window), 3)
    return history


def _build_ndvi_history(lat: float, lon: float, months: int, now: datetime | None = None) -> list[dict[str, Any]]:
    now = now or datetime.now()
    raw_history = [
        _build_history_point(lat, lon, i, now)
        for i in range(min(months, 24))
    ]
    raw_history.reverse()
    return _enrich_history(raw_history)


def _evaluate_alerts(history: list[dict[str, Any]], reference_date: str | None = None) -> list[dict[str, Any]]:
    if not history:
        return []

    current = history[-1]
    alerts: list[dict[str, Any]] = []
    triggered_at = reference_date or current["date"]

    if len(history) >= 3:
        baseline = history[-3]["ndvi"]
        change_2m = round(current["ndvi"] - baseline, 3)
        if change_2m <= -0.12:
            alerts.append({
                "rule_id": "drop_2m_gt_0_12",
                "severity": "high",
                "title": "Caída abrupta de vigor",
                "probable_cause": "Estrés hídrico o evento climático reciente.",
                "triggered_at": triggered_at,
                "evidence": {
                    "current_ndvi": current["ndvi"],
                    "baseline_ndvi": baseline,
                    "change": change_2m,
                    "moving_avg_3m": current.get("moving_avg_3m"),
                },
            })

    if current["ndvi"] < 0.35:
        alerts.append({
            "rule_id": "critical_low_ndvi",
            "severity": "high",
            "title": "NDVI críticamente bajo",
            "probable_cause": "Daño foliar, plaga o estrés hídrico severo.",
            "triggered_at": triggered_at,
            "evidence": {
                "current_ndvi": current["ndvi"],
                "baseline_ndvi": None,
                "change": None,
                "moving_avg_3m": current.get("moving_avg_3m"),
            },
        })

    if len(history) >= 4:
        last_changes = [point.get("monthly_change", 0) for point in history[-3:]]
        total_change = round(sum(last_changes), 3)
        if all(change is not None and change < 0 for change in last_changes) and total_change <= -0.15:
            alerts.append({
                "rule_id": "persistent_decline_3m",
                "severity": "medium",
                "title": "Deterioro sostenido",
                "probable_cause": "Problemas de manejo agronómico o déficit hídrico acumulado.",
                "triggered_at": triggered_at,
                "evidence": {
                    "current_ndvi": current["ndvi"],
                    "baseline_ndvi": history[-4]["ndvi"],
                    "change": total_change,
                    "moving_avg_3m": current.get("moving_avg_3m"),
                },
            })

    if len(history) >= 6:
        recent = [point["ndvi"] for point in history[-6:]]
        volatility = statistics.pstdev(recent)
        if volatility >= 0.1:
            alerts.append({
                "rule_id": "high_ndvi_volatility",
                "severity": "low",
                "title": "Alta volatilidad de NDVI",
                "probable_cause": "Variabilidad fenológica o heterogeneidad del lote.",
                "triggered_at": triggered_at,
                "evidence": {
                    "current_ndvi": current["ndvi"],
                    "baseline_ndvi": round(sum(recent) / len(recent), 3),
                    "change": round(volatility, 3),
                    "moving_avg_3m": current.get("moving_avg_3m"),
                },
            })

    severity_order = {"high": 0, "medium": 1, "low": 2}
    alerts.sort(key=lambda alert: severity_order.get(alert["severity"], 3))
    return alerts


def _build_alert_evidence(alerts: list[dict[str, Any]], ndvi: float) -> dict[str, Any]:
    if not alerts:
        return {"has_alerts": False, "ndvi": round(ndvi, 3)}

    return {
        "has_alerts": True,
        "alert_count": len(alerts),
        "highest_severity": alerts[0]["severity"],
        "rules": [alert["rule_id"] for alert in alerts],
        "ndvi": round(ndvi, 3),
    }
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
        "network": os.getenv("STELLAR_NETWORK", "testnet"),
        "metrics": dict(LATEST_STAGE_METRICS),
        "timeouts_s": dict(DEFAULT_SERVICE_TIMEOUTS),
        "circuit_breakers": {
            name: breaker.snapshot()
            for name, breaker in SERVICE_BREAKERS.items()
        },
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
        health["stellar_metrics"] = stellar_adapter.get_metrics()
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
    1. Consulta datos satelitales (NDVI + NDMI)
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
    satellite_start = time.perf_counter()
    try:
        sat_data = await _execute_with_timeout_and_breaker(
            "satellite",
            retry_satellite(request.lat, request.lon),
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Satellite service error: {e}") from e
    LATEST_STAGE_METRICS["satellite_ms"] = round((time.perf_counter() - satellite_start) * 1000, 2)
    if sat_data["status"] == "error":
        logger.error(f"Satellite error: {sat_data['message']}")
        raise HTTPException(status_code=400, detail=sat_data["message"])

    ndvi = sat_data.get("ndvi", 0)
    ndmi = sat_data.get("ndmi", 0)
    stress_context = get_water_stress_level(ndmi)
    history_for_alerts = _build_ndvi_history(request.lat, request.lon, 6)
    alerts = _evaluate_alerts(history_for_alerts, reference_date=datetime.now().strftime("%Y-%m"))
    geolocation = validate_geolocation(request.lat, request.lon)
    regional_benchmark = compute_regional_benchmark(
        ndvi=ndvi,
        region_key=geolocation.get("region_key"),
        region_name=geolocation.get("region"),
    )
    
    # Agregar avg_ndvi regional para reasoning agent
    sat_data["regional_avg_ndvi"] = geolocation.get("avg_ndvi")

    # 2. Validación (siempre se devuelve un objeto consistente)
    validation_result: dict[str, Any] = {
        "all_valid": False,
        "can_verify": False,
        "validations": {
            "geolocation": validate_geolocation(request.lat, request.lon),
            "vegetation": validate_vegetation(ndvi),
            "contract": None,
            "token": None,
            "certificate": None,
        },
    }

    if request.asset_address and request.token_id:
        # Validación extendida si además se recibe información de asset/token
        try:
            full_validation = validate_vineyard(
                request.lat, request.lon, ndvi,
                request.asset_address, request.token_id,
                None, None  # Sin web3
            )
        except Exception as exc:
            logger.warning("Extended validation unavailable: %s", exc)
            full_validation = {
                "all_valid": validation_result["all_valid"],
                "can_verify": validation_result["can_verify"],
                "validations": {
                    "contract": {
                        "valid": False,
                        "message": "Extended contract validation unavailable",
                    },
                    "token": {
                        "valid": False,
                        "exists": False,
                        "message": "Extended token validation unavailable",
                    },
                    "certificate": {
                        "exists": False,
                        "message": "Extended certificate validation unavailable",
                    },
                },
            }
        validation_result.update(
            {
                "all_valid": full_validation.get("all_valid", validation_result["all_valid"]),
                "can_verify": full_validation.get("can_verify", validation_result["can_verify"]),
                "validations": {
                    **validation_result["validations"],
                    **full_validation.get("validations", {}),
                },
            }
        )
        regional_benchmark = validation_result["validations"]["regional_benchmark"]
        logger.info(
            f"Validation: geoloc={validation_result['validations']['geolocation']['valid']}, "
            f"vegetation={validation_result['validations']['vegetation']['valid']}"
        )
    else:
        validation_result["all_valid"] = (
            validation_result["validations"]["geolocation"]["valid"]
            and validation_result["validations"]["vegetation"]["valid"]
        )
        validation_result["can_verify"] = validation_result["all_valid"]
        logger.info(
            "Validation (partial): geoloc=%s, vegetation=%s",
            validation_result["validations"]["geolocation"]["valid"],
            validation_result["validations"]["vegetation"]["valid"],
        )

    # 3. Análisis con IA
    logger.info("AI analyzing vineyard health")
    satellite_image_task = asyncio.create_task(
        _get_satellite_image_base64(request.lat, request.lon, ndvi)
    )
    ai_start = time.perf_counter()
    try:
        verdict = await _execute_with_timeout_and_breaker(
            "ai",
            retry_ai_analysis(sat_data),
        )
    except Exception as e:
        satellite_image_task.cancel()
        raise HTTPException(status_code=503, detail=f"AI service error: {e}") from e
    LATEST_STAGE_METRICS["ai_ms"] = round((time.perf_counter() - ai_start) * 1000, 2)

    # Generar imágenes y evidencia auditable
    satellite_img = await _get_satellite_image_base64(request.lat, request.lon, ndvi, layer="ndvi")
    ndmi_img = await _get_satellite_image_base64(request.lat, request.lon, ndvi, layer="ndmi")
    ndmi = round(max(-1.0, min(1.0, (ndvi - 0.2) * 0.8)), 3)

    processed_image_bytes, processed_image_mime = _decode_data_uri_image(ndmi_img)
    evidence_payload = _build_evidence_payload(
        farm_id=request.farm_id,
        lat=request.lat,
        lon=request.lon,
        ndvi=ndvi,
        ndmi=ndmi,
        justification=verdict["justification"],
        processed_image_bytes=processed_image_bytes,
        processed_image_mime=processed_image_mime,
    )

    try:
        evidence_upload = await _upload_evidence_to_ipfs(
            evidence_payload=evidence_payload,
            processed_image_bytes=processed_image_bytes,
            image_mime_type=processed_image_mime,
        )
    except Exception as e:
        logger.error(f"Evidence upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Evidence upload failed: {e}")

    # 4. Notarización en Hedera (Trust Layer)
    logger.info("Notarizing in Hedera HCS")
    topic_id = os.getenv("HEDERA_TOPIC_ID")
    if not topic_id:
        raise HTTPException(status_code=500, detail="HEDERA_TOPIC_ID not configured")
    if not hedera_node:
        raise HTTPException(status_code=503, detail="Hedera not configured")

    hedera_start = time.perf_counter()
    hedera_payload = {
        "farm_id": request.farm_id,
        "coordinates": {"lat": request.lat, "lon": request.lon},
        "ndvi": ndvi,
        "ndmi": ndmi,
        "score": verdict.get("score"),
        "risk_level": verdict.get("risk_level"),
        "justification": verdict.get("justification"),
        "score_model_version": verdict.get("score_model_version", SCORE_MODEL_VERSION),
        "score_breakdown": verdict.get("score_breakdown", {}),
        "evidence_cid": evidence_upload["evidence_cid"],
        "alerts": _build_alert_evidence(alerts, ndvi),
        "investment_analysis": verdict.get("investment_analysis", {}),
        "metrics": verdict.get("metrics", {}),
    }

    try:
        hedera_result = await _execute_with_timeout_and_breaker(
            "hedera",
            retry_hedera(topic_id, hedera_payload),
        )
    except Exception as e:
        satellite_image_task.cancel()
        raise HTTPException(status_code=503, detail=f"Hedera service error: {e}") from e
    LATEST_STAGE_METRICS["hedera_ms"] = round((time.perf_counter() - hedera_start) * 1000, 2)
    hedera_status = hedera_result.get("status", "UNKNOWN")
    hedera_txn_id = hedera_result.get("transaction_id", "")

    # Notarizar alerta de estrés hídrico si aplica
    report_ref = f"/certificate/{request.farm_id}"
    if stress_context["level"] == "critical":
        alert_payload = {
            "type": "WATER_STRESS",
            "farm_id": request.farm_id,
            "lvl": "critical",
            "ndmi": round(ndmi, 3),
            "ref": report_ref,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        logger.warning(f"Critical NDMI detected, sending Hedera alert for {request.farm_id}")
        alert_hedera_status = await retry_hedera(topic_id, alert_payload)
        ALERT_HISTORY.setdefault(request.farm_id, []).append(
            {
                "farm_id": request.farm_id,
                "level": "critical",
                "ndmi": round(ndmi, 3),
                "phenology_stage": stress_context["phenology_stage"],
                "report_ref": report_ref,
                "hedera_status": alert_hedera_status,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    # 5. Actualizar en Stellar Soroban (Asset Layer)
    logger.info("Updating VitisScore in Stellar Soroban")

    # Convertir hedera_txn_id a bytes (32 bytes)
    hedera_txn_bytes = hedera_txn_id.encode()[:32].ljust(32, b"0") if hedera_txn_id else b"0" * 32

    try:
        stellar_start = time.perf_counter()

        # 5a. Registrar ubicación si es la primera certificación
        has_existing_location = False
        try:
            has_existing_location = await stellar_adapter.has_location(request.farm_id)
        except NotImplementedError:
            has_existing_location = False  # En stub mode, assumed false
        
        if not has_existing_location:
            logger.info(f"First certification: registering location for {request.farm_id}")
            geohash = f"{request.lat:.4f},{request.lon:.4f}"  # Simple geohash approximation
            location_tx_hash = await stellar_adapter.register_location(
                farm_id=request.farm_id,
                lat=request.lat,
                lon=request.lon,
                geohash=geohash,
            )
            logger.info(f"Location registered: {location_tx_hash}")

        stellar_tx_hash = await _execute_with_timeout_and_breaker(
            "stellar",
            stellar_adapter.update_vitis_score(
                farm_id=request.farm_id,
                score=int(verdict["score"]),
                hedera_txn_id=hedera_txn_bytes,
                evidence_cid=evidence_upload["evidence_cid"],
            ),
        )
        LATEST_STAGE_METRICS["stellar_ms"] = round((time.perf_counter() - stellar_start) * 1000, 2)
    except Exception as e:
        satellite_image_task.cancel()
        logger.error(f"Stellar update failed: {e}")
        raise HTTPException(status_code=500, detail=f"Stellar update failed: {e}")

    # Imagen satelital (en paralelo con IA/ledgers)
    satellite_img = await satellite_image_task
    evidence_index = _read_evidence_index()
    evidence_index[request.farm_id] = {
        "farm_id": request.farm_id,
        "evidence_cid": evidence_upload["evidence_cid"],
        "evidence_json_cid": evidence_upload["evidence_json_cid"],
        "image_cid": evidence_upload["image_cid"],
        "gateway_url": evidence_upload["gateway_url"],
        "timestamp": evidence_payload["timestamp"],
        "provider": evidence_upload["provider"],
    }
    _write_evidence_index(evidence_index)

    logger.info(f"Audit complete. TX: {stellar_tx_hash}")

    return AuditResponse(
        vitis_score=verdict["score"],
        risk=verdict["risk_level"],
        justification=verdict["justification"],
        ndvi=ndvi,
        ndmi=ndmi,
        water_stress_level=stress_context["level"],
        satellite_img=satellite_img,
        hedera_notarization=hedera_status,
        stellar_tx_hash=stellar_tx_hash,
        hedera_txn_id=hedera_txn_id,
        evidence_cid=evidence_upload["evidence_cid"],
        status="ASSET_CERTIFIED",
        alerts=alerts,
        regional_benchmark=regional_benchmark,
        score_model_version=verdict.get("score_model_version", SCORE_MODEL_VERSION),
        score_breakdown=verdict.get("score_breakdown", {}),
        investment_analysis=verdict.get("investment_analysis"),
        validation=validation_result,
        lat=request.lat,
        lon=request.lon,
        source=sat_data.get("source"),
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


@app.get("/evidence/{farm_id}")
async def get_evidence(farm_id: str) -> dict[str, Any]:
    """
    Resuelve el CID de evidencia por farm_id y devuelve links verificables.
    """
    gateway_base = os.getenv("IPFS_GATEWAY_BASE", "https://ipfs.io/ipfs")
    evidence_index = _read_evidence_index()
    entry = evidence_index.get(farm_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Evidence not found for farm_id")

    evidence_cid = entry["evidence_cid"]
    evidence_json_cid = entry.get("evidence_json_cid", evidence_cid)
    image_cid = entry.get("image_cid")

    return {
        "farm_id": farm_id,
        "evidence_cid": evidence_cid,
        "evidence_json_cid": evidence_json_cid,
        "image_cid": image_cid,
        "gateway_url": entry.get("gateway_url", f"{gateway_base}/{evidence_cid}"),
        "evidence_json_url": f"{gateway_base}/{evidence_json_cid}",
        "processed_image_url": f"{gateway_base}/{image_cid}" if image_cid else None,
        "timestamp": entry.get("timestamp"),
        "provider": entry.get("provider"),
    }
@app.get("/alerts/{farm_id}")
async def get_alerts(farm_id: str) -> dict[str, Any]:
    """Devuelve historial de alertas de estrés hídrico para una finca."""
    return {
        "farm_id": farm_id,
        "alerts": ALERT_HISTORY.get(farm_id, []),
        "count": len(ALERT_HISTORY.get(farm_id, [])),
    }


@app.get("/arbitration/config")
async def get_arbitration_config() -> dict[str, Any]:
    return {
        "initial_arbitrator": INITIAL_ARBITRATOR,
        "scoring_model_version": _current_scoring_model_version,
        "min_dispute_bond": MIN_DISPUTE_BOND,
    }


@app.post("/arbitration/scoring-model")
async def update_scoring_model(request: UpdateScoringModelRequest) -> dict[str, Any]:
    global _current_scoring_model_version

    if request.version <= _current_scoring_model_version:
        raise HTTPException(status_code=400, detail="Version must increase")

    previous = _current_scoring_model_version
    _current_scoring_model_version = request.version

    payload = {
        "type": "SCORING_MODEL_UPDATED",
        "previous_version": previous,
        "new_version": request.version,
        "updated_by": request.updated_by,
        "changelog": request.changelog,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    hedera_status, hedera_txn_id = await _notarize_dispute_payload(payload)
    return {
        "previous_version": previous,
        "current_version": _current_scoring_model_version,
        "hedera_status": hedera_status,
        "hedera_txn_id": hedera_txn_id,
    }


@app.post("/disputes/open", response_model=DisputeResponse)
async def open_dispute(request: OpenDisputeRequest) -> DisputeResponse:
    if request.bond < MIN_DISPUTE_BOND:
        raise HTTPException(
            status_code=400,
            detail=f"Bond too low. Minimum required: {MIN_DISPUTE_BOND}"
        )

    async with _disputes_lock:
        current = _disputes.get(request.record_id)
        if current and current["status"] == "OPEN":
            raise HTTPException(status_code=409, detail="Dispute already open for record")

        created_at = datetime.now(timezone.utc).isoformat()
        payload = {
            "record_id": request.record_id,
            "type": "DISPUTE_OPENED",
            "bond": request.bond,
            "challenger": request.challenger,
            "reason": request.reason,
            "scoring_model_version": _current_scoring_model_version,
            "arbitrator_mode": "CENTRALIZED",
            "initial_arbitrator": INITIAL_ARBITRATOR,
            "created_at": created_at,
        }
        hedera_status, hedera_txn_id = await _notarize_dispute_payload(payload)

        stored = {
            "record_id": request.record_id,
            "status": "OPEN",
            "bond": request.bond,
            "challenger": request.challenger,
            "resolver": None,
            "verdict": None,
            "hedera_status": hedera_status,
            "hedera_txn_id": hedera_txn_id,
            "scoring_model_version": _current_scoring_model_version,
            "created_at": created_at,
            "resolved_at": None,
        }
        _disputes[request.record_id] = stored

    return DisputeResponse(**stored)


@app.post("/disputes/resolve", response_model=DisputeResponse)
async def resolve_dispute(request: ResolveDisputeRequest) -> DisputeResponse:
    async with _disputes_lock:
        dispute = _disputes.get(request.record_id)
        if not dispute:
            raise HTTPException(status_code=404, detail="Dispute not found")
        if dispute["status"] != "OPEN":
            raise HTTPException(status_code=409, detail="Dispute already resolved")

        resolved_at = datetime.now(timezone.utc).isoformat()
        payload = {
            "record_id": request.record_id,
            "type": "DISPUTE_RESOLVED",
            "verdict": request.verdict,
            "resolver": request.resolver,
            "notes": request.notes,
            "scoring_model_version": dispute["scoring_model_version"],
            "resolved_at": resolved_at,
        }
        hedera_status, hedera_txn_id = await _notarize_dispute_payload(payload)

        dispute["status"] = "RESOLVED"
        dispute["resolver"] = request.resolver
        dispute["verdict"] = request.verdict
        dispute["resolved_at"] = resolved_at
        dispute["hedera_status"] = hedera_status
        if hedera_txn_id:
            dispute["hedera_txn_id"] = hedera_txn_id

        return DisputeResponse(**dispute)
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


@app.get("/satellite/layers")
async def satellite_layers(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    from_: str | None = Query(None, alias="from", description="ISO datetime start"),
    to: str | None = Query(None, description="ISO datetime end"),
) -> dict[str, Any]:
    """Devuelve las diferentes capas satelitales (NDVI, NDMI, TrueColor)."""
    layers = {}
    evalscripts = {
        "ndvi": NDVI_EVALSCRIPT,
        "ndmi": NDMI_EVALSCRIPT,
        "truecolor": TRUE_COLOR_EVALSCRIPT
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


@app.get("/satellite/history")
async def satellite_history(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    months: int = Query(24, description="Number of months to look back"),
) -> dict[str, Any]:
    """Devuelve el historial NDVI de los últimos N meses."""
    history = _build_ndvi_history(lat, lon, months)
    alerts = _evaluate_alerts(history)

    return {
        "history": history,
        "alerts": alerts,
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
