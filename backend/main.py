# ============================================
# VitisTrust API - Production Server
# ============================================
# Run with: uvicorn backend.main:app --host 0.0.0.0 --port $PORT
# ============================================

import asyncio
import base64
import hashlib
import inspect
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from agents.perception_agent import get_real_indices, get_water_stress_level
from agents.reasoning_agent import SCORE_MODEL_VERSION, analyze_vineyard_health
from agents.validation_agent import validate_geolocation, validate_vegetation, validate_vineyard
from backend import deps
from backend.benchmarks import compute_regional_benchmark, get_region_baseline, list_benchmarks
from backend.dispute_ops import load_disputes_store
from backend.routers import disputes, satellite
from backend.schemas import AuditRequest, AuditResponse
from backend.security import check_verify_rate_limit, cors_credentials_allowed, get_cors_origins
from backend.satellite_ops import (
    _build_alert_evidence,
    _build_ndvi_history,
    _decode_data_uri_image,
    _evaluate_alerts,
    _get_satellite_image_base64,
)
from backend.state import ALERT_HISTORY

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("vitistrust")

_cors_origins = get_cors_origins()

app = FastAPI(
    title="VitisTrust Oracle API",
    version="3.0.0",
    description="Satellite-verified NFT certification (Hedera + Rootstock)",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=cors_credentials_allowed(_cors_origins),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(satellite.router)
app.include_router(disputes.router)

# ============================================
# Configuración
# ============================================

MAX_RETRIES = 3
RETRY_DELAYS = [1, 2, 5]
DEFAULT_SERVICE_TIMEOUTS = {
    "satellite": float(os.getenv("SATELLITE_TIMEOUT_S", "25")),
    "ai": float(os.getenv("AI_TIMEOUT_S", "35")),
    "hedera": float(os.getenv("HEDERA_TIMEOUT_S", "20")),
    "rootstock": float(os.getenv("ROOTSTOCK_TIMEOUT_S", "120")),
}

EVIDENCE_INDEX_PATH = Path(os.getenv("EVIDENCE_INDEX_PATH", "backend/data/evidence_index.json"))
EVIDENCE_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)


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
            logger.warning("Circuit breaker opened for %s", self.name)

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
    "rootstock": CircuitBreaker("rootstock"),
}

LATEST_STAGE_METRICS: dict[str, float] = {
    "satellite_ms": 0.0,
    "ai_ms": 0.0,
    "hedera_ms": 0.0,
    "rootstock_ms": 0.0,
}


def retry_on_failure(max_retries: int = MAX_RETRIES, delays: list = RETRY_DELAYS):
    def decorator(func):
        def _log_retry(attempt: int, error: Exception):
            delay = delays[attempt]
            logger.warning(
                "%s failed (attempt %s/%s), retrying in %ss: %s",
                func.__name__,
                attempt + 1,
                max_retries,
                delay,
                error,
            )
            return delay

        def _log_failure(error: Exception):
            logger.error("%s failed after %s attempts: %s", func.__name__, max_retries, error)

        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                last_error = None
                for attempt in range(max_retries):
                    try:
                        return await func(*args, **kwargs)
                    except Exception as exc:
                        last_error = exc
                        if attempt < max_retries - 1:
                            delay = _log_retry(attempt, exc)
                            await asyncio.sleep(delay)
                        else:
                            _log_failure(exc)
                raise last_error

            return async_wrapper

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    last_error = exc
                    if attempt < max_retries - 1:
                        delay = _log_retry(attempt, exc)
                        time.sleep(delay)
                    else:
                        _log_failure(exc)
            raise last_error

        return sync_wrapper

    return decorator


deps.init_adapters()
load_disputes_store()

hedera_node = deps.hedera_node
rootstock_adapter = deps.rootstock_adapter

retry_decorator = retry_on_failure()


@retry_decorator
async def retry_satellite(lat: float, lon: float) -> dict[str, Any]:
    return get_real_indices(lat, lon)


@retry_decorator
async def retry_ai_analysis(sat_data: dict[str, Any]) -> dict[str, Any]:
    return analyze_vineyard_health(sat_data)


@retry_decorator
async def retry_hedera(topic_id: str, verdict: dict[str, Any]) -> dict[str, str]:
    if not deps.hedera_node:
        raise RuntimeError("Hedera not configured")
    return deps.hedera_node.notarize_vitis_report(topic_id, verdict)


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


# ============================================
# Endpoints
# ============================================


@app.get("/health")
async def health_check() -> dict[str, Any]:
    """Verifica el estado de las conexiones a Hedera y Rootstock."""
    health = {
        "status": "healthy",
        "hedera": "unknown",
        "rootstock": "unknown",
        "network": os.getenv("RSK_NETWORK", "rsk-testnet"),
        "metrics": dict(LATEST_STAGE_METRICS),
        "timeouts_s": dict(DEFAULT_SERVICE_TIMEOUTS),
        "circuit_breakers": {
            name: breaker.snapshot()
            for name, breaker in SERVICE_BREAKERS.items()
        },
    }

    try:
        if deps.hedera_node is not None and deps.hedera_node.client is not None:
            health["hedera"] = "connected"
        else:
            health["hedera"] = "not configured"
    except Exception:
        health["hedera"] = "error"
        health["status"] = "degraded"

    adapter = deps.rootstock_adapter
    if adapter is not None:
        health["rootstock"] = "configured"
        health["rootstock_metrics"] = adapter.get_metrics()
        if getattr(adapter, "is_stub", False):
            health["rootstock"] = "configured (stub)"
    else:
        health["rootstock"] = "not configured"

    if health["hedera"] == "error":
        health["status"] = "degraded"

    return health


@app.post("/verify-vineyard")
async def verify_vineyard(
    request: AuditRequest,
    _: None = Depends(check_verify_rate_limit),
) -> AuditResponse:
    """Audita un viñedo tokenizado."""
    logger.info("Starting audit for farm: %s", request.farm_id)

    adapter = deps.rootstock_adapter
    if not adapter:
        raise HTTPException(
            status_code=503,
            detail="Rootstock adapter not available - asset layer unavailable",
        )

    logger.info("Consulting satellite for %s, %s", request.lat, request.lon)
    satellite_start = time.perf_counter()
    try:
        sat_data = await _execute_with_timeout_and_breaker(
            "satellite",
            retry_satellite(request.lat, request.lon),
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Satellite service error: {exc}") from exc
    LATEST_STAGE_METRICS["satellite_ms"] = round((time.perf_counter() - satellite_start) * 1000, 2)
    if sat_data["status"] == "error":
        logger.error("Satellite error: %s", sat_data["message"])
        raise HTTPException(status_code=400, detail=sat_data["message"])

    ndvi = float(sat_data.get("ndvi", 0) or 0)
    ndmi = round(float(sat_data.get("ndmi", 0) or 0), 3)
    stress_context = get_water_stress_level(ndmi)
    history_for_alerts = _build_ndvi_history(request.lat, request.lon, 6)
    alerts = _evaluate_alerts(history_for_alerts, reference_date=datetime.now().strftime("%Y-%m"))
    geolocation = validate_geolocation(request.lat, request.lon)
    regional_benchmark = compute_regional_benchmark(
        ndvi=ndvi,
        region_key=geolocation.get("region_key"),
        region_name=geolocation.get("region"),
    )

    sat_data["regional_avg_ndvi"] = geolocation.get("avg_ndvi")

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

    if request.asset_address and request.token_id is not None:
        w3 = getattr(adapter, "_w3", None) if adapter else None
        vitis_contract = getattr(adapter, "_contract", None) if adapter else None
        on_chain_ready = (
            w3 is not None
            and vitis_contract is not None
            and not getattr(adapter, "is_stub", True)
        )
        try:
            if on_chain_ready:
                full_validation = validate_vineyard(
                    request.lat,
                    request.lon,
                    ndvi,
                    request.asset_address,
                    request.token_id,
                    w3,
                    vitis_contract,
                )
            else:
                raise RuntimeError("Rootstock stub/unavailable — skipping on-chain validation")
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
            "Validation: geoloc=%s, vegetation=%s",
            validation_result["validations"]["geolocation"]["valid"],
            validation_result["validations"]["vegetation"]["valid"],
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
    except Exception as exc:
        satellite_image_task.cancel()
        raise HTTPException(status_code=503, detail=f"AI service error: {exc}") from exc
    LATEST_STAGE_METRICS["ai_ms"] = round((time.perf_counter() - ai_start) * 1000, 2)

    satellite_img = await _get_satellite_image_base64(request.lat, request.lon, ndvi, layer="ndvi")
    ndmi_img = await _get_satellite_image_base64(request.lat, request.lon, ndvi, layer="ndmi")

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
    except Exception as exc:
        logger.error("Evidence upload failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Evidence upload failed: {exc}") from exc

    logger.info("Notarizing in Hedera HCS")
    topic_id = os.getenv("HEDERA_TOPIC_ID")
    if not topic_id:
        raise HTTPException(status_code=500, detail="HEDERA_TOPIC_ID not configured")
    if not deps.hedera_node:
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
    except Exception as exc:
        satellite_image_task.cancel()
        raise HTTPException(status_code=503, detail=f"Hedera service error: {exc}") from exc
    LATEST_STAGE_METRICS["hedera_ms"] = round((time.perf_counter() - hedera_start) * 1000, 2)
    hedera_status = hedera_result.get("status", "UNKNOWN")
    hedera_txn_id = hedera_result.get("transaction_id", "")

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
        logger.warning("Critical NDMI detected, sending Hedera alert for %s", request.farm_id)
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

    logger.info("Certifying asset on Rootstock (VitisRegistry)")

    hedera_topic_ref = (hedera_txn_id.strip() if hedera_txn_id else "") or topic_id
    _stub_asset = "0x0000000000000000000000000000000000000001"

    if not adapter.is_stub:
        if not request.asset_address or request.token_id is None:
            raise HTTPException(
                status_code=400,
                detail="asset_address and token_id are required when Rootstock is fully configured "
                "(RSK_RPC_URL, RSK_CONTRACT_ADDRESS, RSK_PRIVATE_KEY)",
            )
        asset_for_tx = request.asset_address
        token_for_tx = request.token_id
    else:
        asset_for_tx = request.asset_address or _stub_asset
        token_for_tx = request.token_id if request.token_id is not None else 0

    try:
        rsk_start = time.perf_counter()
        rootstock_tx_hash = await _execute_with_timeout_and_breaker(
            "rootstock",
            adapter.certify_asset(
                asset_address=asset_for_tx,
                token_id=token_for_tx,
                score=int(verdict["score"]),
                hedera_topic_ref=hedera_topic_ref,
                farm_id=request.farm_id,
            ),
        )
        LATEST_STAGE_METRICS["rootstock_ms"] = round((time.perf_counter() - rsk_start) * 1000, 2)
    except Exception as exc:
        satellite_image_task.cancel()
        logger.error("Rootstock certify failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Rootstock certify failed: {exc}") from exc

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

    logger.info("Audit complete. RSK TX: %s", rootstock_tx_hash)

    return AuditResponse(
        vitis_score=verdict["score"],
        risk=verdict["risk_level"],
        justification=verdict["justification"],
        ndvi=ndvi,
        ndmi=ndmi,
        water_stress_level=stress_context["level"],
        satellite_img=satellite_img,
        hedera_notarization=hedera_status,
        rootstock_tx_hash=rootstock_tx_hash,
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
        rootstock_stub=bool(getattr(adapter, "is_stub", False)),
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
async def get_certificate(
    farm_id: str,
    asset_address: str | None = Query(default=None),
    token_id: int | None = Query(default=None),
) -> dict[str, Any]:
    """Consulta una certificación on-chain en VitisRegistry (Rootstock)."""
    adapter = deps.rootstock_adapter
    if not adapter:
        raise HTTPException(status_code=503, detail="Rootstock not configured")
    if not asset_address or token_id is None:
        raise HTTPException(
            status_code=400,
            detail="Query parameters asset_address and token_id are required",
        )
    if adapter.is_stub:
        raise HTTPException(
            status_code=503,
            detail="On-chain certificate reads require a configured Rootstock RPC, contract and key",
        )
    try:
        record = await adapter.get_certification(asset_address, token_id)
        if record["score"] == 0 and record["timestamp"] == 0 and not record["topic_id"]:
            raise HTTPException(status_code=404, detail="No certification for this asset/token")
        return {
            "farm_id": farm_id,
            "vitis_score": record["score"],
            "timestamp": record["timestamp"],
            "hedera_txn_id": record["topic_id"],
            "scoring_model_version": record["scoring_model_version"],
            "auditor": "VitisTrust Oracle",
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Certificate query failed: %s", exc)
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/evidence/{farm_id}")
async def get_evidence(farm_id: str) -> dict[str, Any]:
    """Resuelve el CID de evidencia por farm_id y devuelve links verificables."""
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


@app.get("/benchmarks/{region}")
async def get_regional_benchmark_endpoint(
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


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
