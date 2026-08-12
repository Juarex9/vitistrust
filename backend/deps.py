"""Shared service adapters initialized at application startup."""

import logging
import os

from agents.protocol_agent import HederaProtocol
from backend.rootstock_adapter import RootstockAdapter, create_rootstock_adapter

logger = logging.getLogger("vitistrust")

hedera_node: HederaProtocol | None = None
rootstock_adapter: RootstockAdapter | None = None


def init_adapters() -> None:
    """Initialize Hedera and Rootstock adapters (idempotent)."""
    global hedera_node, rootstock_adapter

    if hedera_node is None:
        try:
            hedera_node = HederaProtocol()
            logger.info("Hedera Protocol initialized")
        except Exception as exc:
            logger.error("Failed to initialize Hedera: %s", exc)

    if rootstock_adapter is None:
        try:
            rootstock_adapter = create_rootstock_adapter()
            if rootstock_adapter:
                logger.info("Rootstock adapter initialized")
        except Exception as exc:
            logger.error("Failed to initialize Rootstock adapter: %s", exc)
