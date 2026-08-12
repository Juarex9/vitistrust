"""Dispute notarization and JSON persistence."""

import json
import logging
import os
from pathlib import Path
from typing import Any

from backend import deps
from backend.state import get_disputes

logger = logging.getLogger("vitistrust")

DISPUTES_STORE_PATH = Path(os.getenv("DISPUTES_STORE_PATH", "backend/data/disputes.json"))


async def notarize_dispute_payload(payload: dict[str, Any]) -> tuple[Any, str]:
    topic_id = os.getenv("HEDERA_TOPIC_ID")
    if not topic_id:
        return ("HEDERA_TOPIC_NOT_CONFIGURED", "")
    if not deps.hedera_node:
        return ("HEDERA_NOT_CONFIGURED", "")

    try:
        status = deps.hedera_node.notarize_vitis_report(topic_id, payload)
    except Exception as exc:
        logger.warning("Dispute notarization failed: %s", exc)
        return ("HEDERA_ERROR", "")

    return (status, payload.get("hedera_txn_id", ""))


def load_disputes_store() -> None:
    if not DISPUTES_STORE_PATH.exists():
        return

    try:
        data = json.loads(DISPUTES_STORE_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            get_disputes().update(data)
            logger.info("Loaded %s disputes from %s", len(data), DISPUTES_STORE_PATH)
    except Exception as exc:
        logger.warning("Failed to load disputes store: %s", exc)


def save_disputes_store() -> None:
    DISPUTES_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    DISPUTES_STORE_PATH.write_text(
        json.dumps(get_disputes(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
