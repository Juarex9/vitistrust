# backend/rootstock_adapter.py
"""
Rootstock (RSK) — capa de activos (EVM).

Interactúa con VitisRegistry.sol (certifyAsset / getCertification).
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Optional

from web3 import Web3

from backend.constants import VITIS_ABI

logger = logging.getLogger("vitistrust.rootstock")


@dataclass
class RootstockMetrics:
    total_submissions: int = 0
    retry_attempts: int = 0
    rpc_failures: int = 0
    idempotency_hits: int = 0


@dataclass
class RootstockConfig:
    rpc_url: str
    contract_address: str
    private_key: str
    chain_id: int | None


class RootstockAdapter:
    """Cliente async (ejecuta Web3 síncrono en thread pool)."""

    def __init__(self, config: RootstockConfig):
        self.config = config
        self._metrics = RootstockMetrics()
        self._idempotency_cache: dict[str, tuple[str, float]] = {}
        self._idempotency_window_seconds = 60

        self._w3: Web3 | None = None
        self._contract: Any = None
        self._account = None

        zero = "0x0000000000000000000000000000000000000000"
        addr_ok = (
            bool(config.contract_address)
            and Web3.is_address(config.contract_address)
            and config.contract_address.lower() != zero.lower()
        )

        if config.rpc_url and addr_ok:
            self._w3 = Web3(Web3.HTTPProvider(config.rpc_url))
            try:
                if self._w3.is_connected():
                    checksum = Web3.to_checksum_address(config.contract_address)
                    self._contract = self._w3.eth.contract(address=checksum, abi=VITIS_ABI)
                else:
                    logger.warning("Rootstock RPC not reachable")
            except Exception as exc:
                logger.warning("Rootstock init failed: %s", exc)
                self._w3 = None
                self._contract = None

        if config.private_key and self._w3:
            try:
                self._account = self._w3.eth.account.from_key(config.private_key)
            except Exception as exc:
                logger.warning("Invalid RSK_PRIVATE_KEY: %s", exc)
                self._account = None

        logger.info(
            "RootstockAdapter: stub=%s contract=%s",
            self.is_stub,
            config.contract_address or "(none)",
        )

    @property
    def is_stub(self) -> bool:
        return (
            self._contract is None
            or self._w3 is None
            or not self._w3.is_connected()
            or self._account is None
        )

    def get_metrics(self) -> dict[str, float]:
        return {
            "total_submissions": float(self._metrics.total_submissions),
            "retry_attempts": float(self._metrics.retry_attempts),
            "rpc_failures": float(self._metrics.rpc_failures),
            "idempotency_hits": float(self._metrics.idempotency_hits),
            "stub_mode": 1.0 if self.is_stub else 0.0,
        }

    def _idempotency_key(self, asset_address: str, token_id: int, farm_id: str) -> str:
        window = int(time.time() // self._idempotency_window_seconds)
        return f"{farm_id}:{asset_address.lower()}:{token_id}:{window}"

    async def certify_asset(
        self,
        asset_address: str,
        token_id: int,
        score: int,
        hedera_topic_ref: str,
        farm_id: str,
    ) -> str:
        if not 0 <= score <= 100:
            raise ValueError("Score must be between 0 and 100")
        if not hedera_topic_ref or not hedera_topic_ref.strip():
            raise ValueError("hedera_topic_ref required for certifyAsset")
        if not Web3.is_address(asset_address):
            raise ValueError("Invalid asset_contract address")

        key = self._idempotency_key(asset_address, token_id, farm_id)
        if key in self._idempotency_cache:
            cached_hash, ttl = self._idempotency_cache[key]
            if time.time() < ttl:
                self._metrics.idempotency_hits += 1
                return cached_hash

        self._metrics.total_submissions += 1

        if self.is_stub:
            h = f"mock_rsk_{farm_id}_{int(time.time())}"
            self._idempotency_cache[key] = (h, time.time() + self._idempotency_window_seconds)
            return h

        assert self._contract is not None and self._account is not None and self._w3 is not None
        topic_ref = hedera_topic_ref.strip()

        def _send() -> str:
            acct = self._account
            c = self._contract
            w3 = self._w3
            assert acct is not None and c is not None and w3 is not None
            fn = c.functions.certifyAsset(
                Web3.to_checksum_address(asset_address),
                token_id,
                score,
                topic_ref,
            )
            tx = fn.build_transaction(
                {
                    "from": acct.address,
                    "nonce": w3.eth.get_transaction_count(acct.address),
                    "gas": fn.estimate_gas({"from": acct.address}),
                    "gasPrice": w3.eth.gas_price,
                    "chainId": self.config.chain_id or w3.eth.chain_id,
                }
            )
            signed = w3.eth.account.sign_transaction(tx, private_key=self.config.private_key)
            raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
            tx_hash = w3.eth.send_raw_transaction(raw)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
            if receipt["status"] != 1:
                raise RuntimeError("certifyAsset reverted or failed")
            return receipt["transactionHash"].hex()

        try:
            h = await asyncio.to_thread(_send)
        except Exception:
            self._metrics.rpc_failures += 1
            raise

        self._idempotency_cache[key] = (h, time.time() + self._idempotency_window_seconds)
        return h

    async def get_certification(self, asset_address: str, token_id: int) -> dict[str, Any]:
        if not Web3.is_address(asset_address):
            raise ValueError("Invalid asset_contract address")

        if self.is_stub:
            raise NotImplementedError("On-chain read not available in stub mode")

        assert self._contract is not None

        def _read() -> tuple[Any, ...]:
            return self._contract.functions.getCertification(
                Web3.to_checksum_address(asset_address),
                token_id,
            ).call()

        score, ts, topic_id, model_ver = await asyncio.to_thread(_read)
        return {
            "score": int(score),
            "timestamp": int(ts),
            "topic_id": str(topic_id),
            "scoring_model_version": int(model_ver),
        }


def create_rootstock_adapter() -> Optional[RootstockAdapter]:
    rpc = os.getenv("RSK_RPC_URL", "").strip()
    addr = os.getenv("RSK_CONTRACT_ADDRESS", "").strip()
    key = os.getenv("RSK_PRIVATE_KEY", "").strip()
    chain_raw = os.getenv("RSK_CHAIN_ID", "").strip()
    chain_id: int | None = int(chain_raw) if chain_raw.isdigit() else None

    if not addr:
        logger.warning("RSK_CONTRACT_ADDRESS not set — Rootstock adapter in stub mode (mock TX)")

    config = RootstockConfig(
        rpc_url=rpc,
        contract_address=addr,
        private_key=key,
        chain_id=chain_id,
    )
    return RootstockAdapter(config)
