import importlib
import os
import sys
import types
import asyncio
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


@pytest.fixture
def satellite_payload() -> dict:
    return {
        "status": "success",
        "ndvi": 0.71,
        "ndmi": 0.15,
        "coordinates": {"lat": -33.1234, "lon": -68.9876},
        "source": "mock-sentinel",
    }


@pytest.fixture
def ai_verdict_payload() -> dict:
    return {
        "score": 88,
        "risk_level": "low",
        "justification": "Cobertura vegetal consistente y vigorosa.",
        "hedera_txn_id": "0.0.123456@1710000000.000000000",
    }


@pytest.fixture
def certificate_record_payload() -> dict:
    return {
        "score": 88,
        "timestamp": 1710000000,
        "hedera_txn_id": "0.0.123456@1710000000.000000000",
        "auditor": "VitisTrust Oracle",
    }


@pytest.fixture
def expected_verify_schema_fields() -> set[str]:
    return {
        "vitis_score",
        "risk",
        "justification",
        "ndvi",
        "satellite_img",
        "hedera_notarization",
        "rootstock_tx_hash",
        "hedera_txn_id",
        "status",
    }


@pytest.fixture
def backend_module(
    monkeypatch: pytest.MonkeyPatch,
    satellite_payload: dict,
    ai_verdict_payload: dict,
    certificate_record_payload: dict,
):
    """Carga backend.main con mocks para evitar dependencias externas."""

    class MockRootstockAdapter:
        is_stub = True

        def get_metrics(self) -> dict:
            return {"total_submissions": 0.0}

        async def certify_asset(self, **kwargs) -> str:
            return "0xrootstock_mock_001"

        async def get_certification(self, asset_address: str, token_id: int) -> dict:
            return {
                "score": 88,
                "timestamp": 1710000000,
                "topic_id": "0.0.123456@1710000000.000000000",
                "scoring_model_version": 1,
            }

    class MockHederaProtocol:
        def __init__(self):
            self.client = object()

        def notarize_vitis_report(self, topic_id: str, report_data: dict) -> dict:
            assert topic_id
            assert "score" in report_data
            return {"status": "SUCCESS (MOCK)", "transaction_id": "0.0.123456@1710000000.000000000"}

    fake_rootstock_adapter_module = types.ModuleType("backend.rootstock_adapter")
    fake_rootstock_adapter_module.RootstockAdapter = object
    fake_rootstock_adapter_module.create_rootstock_adapter = lambda: MockRootstockAdapter()
    sys.modules["backend.rootstock_adapter"] = fake_rootstock_adapter_module

    monkeypatch.setenv("HEDERA_TOPIC_ID", "0.0.999999")
    monkeypatch.setenv("RSK_NETWORK", "rsk-testnet")
    monkeypatch.setattr("agents.protocol_agent.HederaProtocol", MockHederaProtocol)

    if "backend.main" in sys.modules:
        del sys.modules["backend.main"]

    import backend.main as backend_main

    backend_main = importlib.reload(backend_main)

    monkeypatch.setattr(backend_main, "get_real_indices", lambda lat, lon: satellite_payload)
    monkeypatch.setattr(backend_main, "analyze_vineyard_health", lambda sat_data: ai_verdict_payload)
    async def _mock_sentinel_token():
        return None

    import backend.satellite_ops as satellite_ops

    monkeypatch.setattr(satellite_ops, "_get_sentinel_token", _mock_sentinel_token)

    return backend_main


@pytest.fixture
def api_client(backend_module):
    return TestClient(backend_module.app)


class TestBackendAPI:
    def test_health_endpoint_schema(self, api_client: TestClient):
        response = api_client.get("/health")

        assert response.status_code == 200
        data = response.json()

        assert {"status", "hedera", "rootstock", "network"}.issubset(data.keys())
        assert data["status"] in {"healthy", "degraded"}
        assert data["hedera"] in {"connected", "not configured", "unknown", "error"}
        assert data["rootstock"] in {"configured", "configured (stub)", "not configured", "unknown"}
        assert isinstance(data["network"], str)

    def test_verify_vineyard_post_schema_and_values(
        self,
        api_client: TestClient,
        expected_verify_schema_fields: set[str],
    ):
        payload = {
            "lat": -33.1234,
            "lon": -68.9876,
            "farm_id": "farm-ar-001",
        }

        response = api_client.post("/verify-vineyard", json=payload)

        assert response.status_code == 200
        data = response.json()

        assert expected_verify_schema_fields.issubset(data.keys())
        assert data["vitis_score"] == 88
        assert data["risk"] == "low"
        assert data["status"] == "ASSET_CERTIFIED"
        assert data["hedera_notarization"] == "SUCCESS (MOCK)"
        assert data["rootstock_tx_hash"] == "0xrootstock_mock_001"
        assert data["rootstock_stub"] is True
        assert data["satellite_img"].startswith("data:image/")

    def test_certificate_endpoint_schema(self, api_client: TestClient, backend_module, monkeypatch: pytest.MonkeyPatch):
        adapter = Mock()
        adapter.is_stub = False
        adapter.get_metrics = lambda: {}
        async def _cert(**kwargs):
            return "0xabc"
        adapter.certify_asset = _cert
        async def _gc(asset_address: str, token_id: int):
            return {
                "score": 88,
                "timestamp": 1710000000,
                "topic_id": "0.0.123456@1710000000.000000000",
                "scoring_model_version": 1,
            }
        adapter.get_certification = _gc
        import backend.deps as deps

        monkeypatch.setattr(deps, "rootstock_adapter", adapter)
        monkeypatch.setattr(backend_module, "rootstock_adapter", adapter)

        response = api_client.get(
            "/certificate/farm-ar-001",
            params={"asset_address": "0x1234567890123456789012345678901234567890", "token_id": 1},
        )

        assert response.status_code == 200
        data = response.json()

        assert set(data.keys()) == {
            "farm_id",
            "vitis_score",
            "timestamp",
            "hedera_txn_id",
            "scoring_model_version",
            "auditor",
        }
        assert data["farm_id"] == "farm-ar-001"
        assert isinstance(data["vitis_score"], int)
        assert isinstance(data["timestamp"], int)
        assert isinstance(data["hedera_txn_id"], str)
        assert isinstance(data["auditor"], str)

    def test_satellite_layers_endpoint_schema(self, api_client: TestClient):
        response = api_client.get("/satellite/layers", params={"lat": -33.1234, "lon": -68.9876})

        assert response.status_code == 200
        data = response.json()

        assert set(data.keys()) == {"layers", "coordinates"}
        assert set(data["layers"].keys()) == {"ndvi", "ndmi", "truecolor"}
        assert data["layers"]["ndvi"].startswith("data:image/")
        assert data["layers"]["ndmi"].startswith("data:image/")
        assert data["layers"]["truecolor"].startswith("data:image/")
        assert data["coordinates"] == {"lat": -33.1234, "lon": -68.9876}

    def test_satellite_history_endpoint_schema(self, api_client: TestClient):
        response = api_client.get(
            "/satellite/history",
            params={"lat": -33.1234, "lon": -68.9876, "months": 6},
        )

        assert response.status_code == 200
        data = response.json()

        assert {"history", "coordinates", "months_analyzed", "source", "demo"}.issubset(data.keys())
        assert data["months_analyzed"] == 6
        assert data["coordinates"] == {"lat": -33.1234, "lon": -68.9876}
        assert data["source"] == "synthetic_demo"
        assert data["demo"] is True
        assert isinstance(data["history"], list)
        assert len(data["history"]) == 6

        for item in data["history"]:
            assert {"date", "ndvi", "status"}.issubset(item.keys())
            assert "monthly_change" in item
            assert "moving_avg_3m" in item
            assert isinstance(item["date"], str)
            assert isinstance(item["ndvi"], float)
            assert item["status"] in {"healthy", "moderate", "stressed"}


class TestBackend:
    """Tests adicionales del backend (sin fixture de mocks)."""

    def test_verify_endpoint_missing_params(self):
        """Test verification with missing parameters."""
        from fastapi.testclient import TestClient

        from backend.main import app

        client = TestClient(app)

        response = client.get("/verify-vineyard")
        assert response.status_code == 422


class TestRetryLogic:
    """Tests for retry logic in backend."""

    @staticmethod
    def _get_retry_on_failure():
        from backend.main import retry_on_failure

        return retry_on_failure
    
    def test_retry_decorator_sync(self):
        """Test retry decorator with sync function."""
        retry_on_failure = self._get_retry_on_failure()
        
        attempt_count = 0
        
        @retry_on_failure(max_retries=3, delays=[0.01, 0.01])
        def flaky_function():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise Exception("Temporary error")
            return "success"
        
        result = flaky_function()
        assert result == "success"
        assert attempt_count == 3

    def test_retry_decorator_async(self):
        """Test retry decorator with async function."""
        retry_on_failure = self._get_retry_on_failure()

        attempt_count = 0

        @retry_on_failure(max_retries=3, delays=[0.01, 0.01])
        async def flaky_async_function():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise Exception("Temporary error")
            return "success"

        result = asyncio.run(flaky_async_function())
        assert result == "success"
        assert attempt_count == 3
    
    def test_retry_decorator_failure(self):
        """Test retry decorator when all attempts fail."""
        retry_on_failure = self._get_retry_on_failure()
        
        attempt_count = 0
        
        @retry_on_failure(max_retries=3, delays=[0.01, 0.01, 0.01])
        def always_fails():
            nonlocal attempt_count
            attempt_count += 1
            raise Exception("Permanent error")
        
        with pytest.raises(Exception):
            always_fails()
        
        assert attempt_count == 3

    def test_retry_decorator_async_failure(self):
        """Test retry decorator when async function fails all attempts."""
        retry_on_failure = self._get_retry_on_failure()

        attempt_count = 0

        @retry_on_failure(max_retries=3, delays=[0.01, 0.01, 0.01])
        async def always_fails_async():
            nonlocal attempt_count
            attempt_count += 1
            raise Exception("Permanent error")

        with pytest.raises(Exception):
            asyncio.run(always_fails_async())

        assert attempt_count == 3


class TestProtocolAgent:
    """Tests for protocol agent mock mode."""

    def test_hedera_protocol_mock_topic_and_notarization(self):
        """Mock mode should create topic and notarize without exceptions."""
        from agents.protocol_agent import HederaProtocol, SUCCESS_MOCK

        protocol = HederaProtocol(is_mock=True)
        topic_id = protocol.create_audit_topic()
        assert topic_id is not None
        assert topic_id.startswith("0.0.")

        result = protocol.notarize_vitis_report(topic_id, {"audit": "ok"})
        assert isinstance(result, dict)
        assert "SUCCESS" in result["status"]
        assert result.get("transaction_id")
        # SUCCESS_MOCK constant retained for backwards-compat naming
        assert SUCCESS_MOCK.startswith("SUCCESS")
