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
from datetime import datetime, timezone
import statistics
from datetime import datetime, timedelta
import time
from typing import Any
from functools import wraps
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from agents.perception_agent import get_real_ndvi
from agents.reasoning_agent import SCORE_MODEL_VERSION, analyze_vineyard_health
from agents.protocol_agent import HederaProtocol
from agents.validation_agent import validate_geolocation, validate_vineyard
from backend.benchmarks import compute_regional_benchmark, get_region_baseline, list_benchmarks
from agents.validation_agent import (
    validate_vineyard,
    validate_geolocation,
    validate_vegetation,
)
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
    satellite_img: str
    hedera_notarization: str
    stellar_tx_hash: str
    hedera_txn_id: str
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
    return get_real_ndvi(lat, lon)


@retry_decorator
async def retry_ai_analysis(sat_data: dict[str, Any]) -> dict[str, Any]:
    return analyze_vineyard_health(sat_data)


@retry_decorator
async def retry_hedera(topic_id: str, verdict: dict[str, Any]) -> str:
    if not hedera_node:
        raise RuntimeError("Hedera not configured")
    return hedera_node.notarize_vitis_report(topic_id, verdict)


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
    history_for_alerts = _build_ndvi_history(request.lat, request.lon, 6)
    alerts = _evaluate_alerts(history_for_alerts, reference_date=datetime.now().strftime("%Y-%m"))
    geolocation = validate_geolocation(request.lat, request.lon)
    regional_benchmark = compute_regional_benchmark(
        ndvi=ndvi,
        region_key=geolocation.get("region_key"),
        region_name=geolocation.get("region"),
    )

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
    verdict = await retry_ai_analysis(sat_data)

    # 4. Notarización en Hedera (Trust Layer)
    logger.info("Notarizing in Hedera HCS")
    topic_id = os.getenv("HEDERA_TOPIC_ID")
    if not topic_id:
        raise HTTPException(status_code=500, detail="HEDERA_TOPIC_ID not configured")
    if not hedera_node:
        raise HTTPException(status_code=503, detail="Hedera not configured")

    notarization_payload = {
        "score": verdict["score"],
        "risk_level": verdict["risk_level"],
        "justification": verdict["justification"],
        "alerts_evidence": _build_alert_evidence(alerts, ndvi),
    }
    hedera_status = await retry_hedera(topic_id, notarization_payload)
    hedera_payload = {
        "farm_id": request.farm_id,
        "coordinates": {"lat": request.lat, "lon": request.lon},
        "ndvi": ndvi,
        "score": verdict.get("score"),
        "risk_level": verdict.get("risk_level"),
        "justification": verdict.get("justification"),
        "score_model_version": verdict.get("score_model_version", SCORE_MODEL_VERSION),
        "score_breakdown": verdict.get("score_breakdown", {}),
        "investment_analysis": verdict.get("investment_analysis", {}),
        "metrics": verdict.get("metrics", {}),
    }

    hedera_status = await retry_hedera(topic_id, hedera_payload)
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
        alerts=alerts,
        regional_benchmark=regional_benchmark,
        score_model_version=verdict.get("score_model_version", SCORE_MODEL_VERSION),
        score_breakdown=verdict.get("score_breakdown", {}),
        status="ASSET_CERTIFIED"
        status="ASSET_CERTIFIED",
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
