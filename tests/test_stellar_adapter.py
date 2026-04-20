import asyncio
from types import SimpleNamespace

import pytest
from stellar_sdk import Keypair, Network
from stellar_sdk.soroban_rpc import GetTransactionStatus

from backend.stellar_adapter import SorobanAdapter, SorobanConfig, StellarNetwork


def _build_adapter() -> SorobanAdapter:
    oracle = Keypair.random()
    config = SorobanConfig(
        network=StellarNetwork.TESTNET,
        rpc_url="https://soroban-testnet.stellar.org:443",
        network_passphrase=Network.TESTNET_NETWORK_PASSPHRASE,
        oracle_keypair=oracle,
        contract_id=oracle.public_key,
    )
    adapter = SorobanAdapter(config)
    adapter._idempotency_window_seconds = 60
    return adapter


def test_detect_sequence_error_markers():
    assert SorobanAdapter._is_sequence_error("tx_bad_seq")
    assert SorobanAdapter._is_sequence_error("bad sequence number")
    assert not SorobanAdapter._is_sequence_error("insufficient fee")


@pytest.mark.asyncio
async def test_wait_for_transaction_timeout():
    adapter = _build_adapter()

    class FakeServer:
        async def get_transaction(self, _tx_hash):
            return SimpleNamespace(status=GetTransactionStatus.NOT_FOUND)

    adapter.server = FakeServer()
    adapter._tx_poll_interval = 0.01
    adapter._tx_poll_timeout = 0.03

    with pytest.raises(TimeoutError):
        await adapter._wait_for_transaction("abc")


@pytest.mark.asyncio
async def test_update_vitis_score_is_idempotent_within_window():
    adapter = _build_adapter()
    adapter._build_idempotency_key = lambda farm_id: f"{farm_id}:fixed-window"
    adapter._get_invocation_data = lambda *_args, **_kwargs: object()

    calls = {"count": 0}

    async def fake_submit_transaction(*_args, **_kwargs):
        calls["count"] += 1
        await asyncio.sleep(0.02)
        return "tx_hash_123"

    adapter._submit_transaction = fake_submit_transaction
    hedera_txn_id = b"a" * 32

    tx_1, tx_2 = await asyncio.gather(
        adapter.update_vitis_score("farm-a", 88, hedera_txn_id),
        adapter.update_vitis_score("farm-a", 88, hedera_txn_id),
    )

    assert tx_1 == "tx_hash_123"
    assert tx_2 == "tx_hash_123"
    assert calls["count"] == 1
    assert adapter.get_metrics()["idempotency_hits"] == 1.0
