"""Tests for Rootstock adapter (stub mode + validation)."""

from __future__ import annotations

import asyncio

import pytest

from backend.rootstock_adapter import RootstockAdapter, RootstockConfig, create_rootstock_adapter


@pytest.fixture
def stub_adapter() -> RootstockAdapter:
    return RootstockAdapter(
        RootstockConfig(
            rpc_url="",
            contract_address="",
            private_key="",
            chain_id=31,
        )
    )


class TestRootstockAdapterStub:
    def test_is_stub_without_contract(self, stub_adapter: RootstockAdapter):
        assert stub_adapter.is_stub is True
        metrics = stub_adapter.get_metrics()
        assert metrics["stub_mode"] == 1.0

    def test_certify_asset_returns_mock_hash(self, stub_adapter: RootstockAdapter):
        tx = asyncio.run(
            stub_adapter.certify_asset(
                asset_address="0x1111111111111111111111111111111111111111",
                token_id=1,
                score=88,
                hedera_topic_ref="0.0.123@1710000000.000000000",
                farm_id="farm-test",
            )
        )
        assert tx.startswith("mock_rsk_farm-test_")

    def test_certify_asset_idempotent_within_window(self, stub_adapter: RootstockAdapter):
        kwargs = dict(
            asset_address="0x1111111111111111111111111111111111111111",
            token_id=7,
            score=70,
            hedera_topic_ref="topic-ref",
            farm_id="farm-idem",
        )
        first = asyncio.run(stub_adapter.certify_asset(**kwargs))
        second = asyncio.run(stub_adapter.certify_asset(**kwargs))
        assert first == second
        assert stub_adapter.get_metrics()["idempotency_hits"] >= 1.0

    def test_certify_rejects_invalid_score(self, stub_adapter: RootstockAdapter):
        with pytest.raises(ValueError, match="Score"):
            asyncio.run(
                stub_adapter.certify_asset(
                    asset_address="0x1111111111111111111111111111111111111111",
                    token_id=1,
                    score=101,
                    hedera_topic_ref="topic",
                    farm_id="farm",
                )
            )

    def test_certify_rejects_invalid_address(self, stub_adapter: RootstockAdapter):
        with pytest.raises(ValueError, match="Invalid asset"):
            asyncio.run(
                stub_adapter.certify_asset(
                    asset_address="not-an-address",
                    token_id=1,
                    score=50,
                    hedera_topic_ref="topic",
                    farm_id="farm",
                )
            )

    def test_get_certification_unavailable_in_stub(self, stub_adapter: RootstockAdapter):
        with pytest.raises(NotImplementedError):
            asyncio.run(
                stub_adapter.get_certification(
                    "0x1111111111111111111111111111111111111111",
                    1,
                )
            )


class TestCreateRootstockAdapter:
    def test_create_without_env_is_stub(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("RSK_CONTRACT_ADDRESS", raising=False)
        monkeypatch.delenv("RSK_RPC_URL", raising=False)
        monkeypatch.delenv("RSK_PRIVATE_KEY", raising=False)
        adapter = create_rootstock_adapter()
        assert adapter is not None
        assert adapter.is_stub is True


class TestIdempotencyKey:
    def test_key_changes_with_token(self, stub_adapter: RootstockAdapter):
        a = stub_adapter._idempotency_key("0xabc", 1, "farm")
        b = stub_adapter._idempotency_key("0xabc", 2, "farm")
        assert a != b
        assert a.startswith("farm:0xabc:1:")
        assert b.startswith("farm:0xabc:2:")
