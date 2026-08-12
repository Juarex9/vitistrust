"""In-memory application state shared across routers."""

import asyncio
import os
from typing import Any

ALERT_HISTORY: dict[str, list[dict[str, Any]]] = {}

_disputes: dict[str, dict[str, Any]] = {}
_disputes_lock = asyncio.Lock()

MIN_DISPUTE_BOND = float(os.getenv("MIN_DISPUTE_BOND", "0.01"))
INITIAL_ARBITRATOR = os.getenv("INITIAL_ARBITRATOR", "INV_ADMIN_MULTISIG")
_current_scoring_model_version = int(os.getenv("SCORING_MODEL_VERSION", "1"))


def get_disputes() -> dict[str, dict[str, Any]]:
    return _disputes


def get_disputes_lock() -> asyncio.Lock:
    return _disputes_lock


def get_scoring_model_version() -> int:
    return _current_scoring_model_version


def set_scoring_model_version(version: int) -> None:
    global _current_scoring_model_version
    _current_scoring_model_version = version
