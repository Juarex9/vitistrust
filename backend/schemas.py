"""Pydantic request/response models for the VitisTrust API."""

from typing import Any

from pydantic import BaseModel, Field


class AuditRequest(BaseModel):
    """Request para iniciar auditoría."""

    lat: float
    lon: float
    farm_id: str
    asset_address: str | None = None
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
    rootstock_tx_hash: str
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
    rootstock_stub: bool = False


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
