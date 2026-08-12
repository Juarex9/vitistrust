"""Arbitration and dispute API routes."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from backend.dispute_ops import notarize_dispute_payload, save_disputes_store
from backend.schemas import (
    DisputeResponse,
    OpenDisputeRequest,
    ResolveDisputeRequest,
    UpdateScoringModelRequest,
)
from backend.security import require_admin_api_key
from backend.state import (
    ALERT_HISTORY,
    INITIAL_ARBITRATOR,
    MIN_DISPUTE_BOND,
    get_disputes,
    get_disputes_lock,
    get_scoring_model_version,
    set_scoring_model_version,
)

router = APIRouter()


@router.get("/alerts/{farm_id}")
async def get_alerts(farm_id: str) -> dict:
    """Devuelve historial de alertas de estrés hídrico para una finca."""
    return {
        "farm_id": farm_id,
        "alerts": ALERT_HISTORY.get(farm_id, []),
        "count": len(ALERT_HISTORY.get(farm_id, [])),
    }


@router.get("/arbitration/config")
async def get_arbitration_config() -> dict:
    return {
        "initial_arbitrator": INITIAL_ARBITRATOR,
        "scoring_model_version": get_scoring_model_version(),
        "min_dispute_bond": MIN_DISPUTE_BOND,
    }


@router.post("/arbitration/scoring-model")
async def update_scoring_model(
    request: UpdateScoringModelRequest,
    _: None = Depends(require_admin_api_key),
) -> dict:
    current_version = get_scoring_model_version()
    if request.version <= current_version:
        raise HTTPException(status_code=400, detail="Version must increase")

    previous = current_version
    set_scoring_model_version(request.version)

    payload = {
        "type": "SCORING_MODEL_UPDATED",
        "previous_version": previous,
        "new_version": request.version,
        "updated_by": request.updated_by,
        "changelog": request.changelog,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    hedera_status, hedera_txn_id = await notarize_dispute_payload(payload)
    return {
        "previous_version": previous,
        "current_version": get_scoring_model_version(),
        "hedera_status": hedera_status,
        "hedera_txn_id": hedera_txn_id,
    }


@router.post("/disputes/open", response_model=DisputeResponse)
async def open_dispute(
    request: OpenDisputeRequest,
    _: None = Depends(require_admin_api_key),
) -> DisputeResponse:
    if request.bond < MIN_DISPUTE_BOND:
        raise HTTPException(
            status_code=400,
            detail=f"Bond too low. Minimum required: {MIN_DISPUTE_BOND}",
        )

    disputes = get_disputes()
    async with get_disputes_lock():
        current = disputes.get(request.record_id)
        if current and current["status"] == "OPEN":
            raise HTTPException(status_code=409, detail="Dispute already open for record")

        created_at = datetime.now(timezone.utc).isoformat()
        payload = {
            "record_id": request.record_id,
            "type": "DISPUTE_OPENED",
            "bond": request.bond,
            "challenger": request.challenger,
            "reason": request.reason,
            "scoring_model_version": get_scoring_model_version(),
            "arbitrator_mode": "CENTRALIZED",
            "initial_arbitrator": INITIAL_ARBITRATOR,
            "created_at": created_at,
        }
        hedera_status, hedera_txn_id = await notarize_dispute_payload(payload)

        stored = {
            "record_id": request.record_id,
            "status": "OPEN",
            "bond": request.bond,
            "challenger": request.challenger,
            "resolver": None,
            "verdict": None,
            "hedera_status": hedera_status,
            "hedera_txn_id": hedera_txn_id,
            "scoring_model_version": get_scoring_model_version(),
            "created_at": created_at,
            "resolved_at": None,
        }
        disputes[request.record_id] = stored
        save_disputes_store()

    return DisputeResponse(**stored)


@router.post("/disputes/resolve", response_model=DisputeResponse)
async def resolve_dispute(
    request: ResolveDisputeRequest,
    _: None = Depends(require_admin_api_key),
) -> DisputeResponse:
    disputes = get_disputes()
    async with get_disputes_lock():
        dispute = disputes.get(request.record_id)
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
        hedera_status, hedera_txn_id = await notarize_dispute_payload(payload)

        dispute["status"] = "RESOLVED"
        dispute["resolver"] = request.resolver
        dispute["verdict"] = request.verdict
        dispute["resolved_at"] = resolved_at
        dispute["hedera_status"] = hedera_status
        if hedera_txn_id:
            dispute["hedera_txn_id"] = hedera_txn_id

        save_disputes_store()
        return DisputeResponse(**dispute)
