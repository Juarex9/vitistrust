import importlib
import os
import sys
import types
from unittest.mock import Mock

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
        "stellar_tx_hash",
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

    class MockStellarAdapter:
        async def update_vitis_score(self, farm_id: str, score: int, hedera_txn_id: bytes) -> str:
            assert farm_id
            assert isinstance(score, int)
            assert isinstance(hedera_txn_id, bytes)
            return "stellar_tx_hash_mock_001"

        async def get_vitis_score(self, farm_id: str) -> dict:
            assert farm_id
            return certificate_record_payload

    class MockHederaProtocol:
        def __init__(self):
            self.client = object()

        def notarize_vitis_report(self, topic_id: str, report_data: dict) -> str:
            assert topic_id
            assert "score" in report_data
            return "SUCCESS (MOCK)"

    fake_stellar_adapter_module = types.ModuleType("backend.stellar_adapter")
    fake_stellar_adapter_module.SorobanAdapter = object
    fake_stellar_adapter_module.create_stellar_adapter = lambda: MockStellarAdapter()
    sys.modules["backend.stellar_adapter"] = fake_stellar_adapter_module

    monkeypatch.setenv("HEDERA_TOPIC_ID", "0.0.999999")
    monkeypatch.setenv("STELLAR_NETWORK", "testnet")
    monkeypatch.setattr("agents.protocol_agent.HederaProtocol", MockHederaProtocol)

    if "backend.main" in sys.modules:
        del sys.modules["backend.main"]

    import backend.main as backend_main

    backend_main = importlib.reload(backend_main)

    monkeypatch.setattr(backend_main, "get_real_ndvi", lambda lat, lon: satellite_payload)
    monkeypatch.setattr(backend_main, "analyze_vineyard_health", lambda sat_data: ai_verdict_payload)
    async def _mock_sentinel_token():
        return None

    monkeypatch.setattr(backend_main, "_get_sentinel_token", _mock_sentinel_token)

    return backend_main


@pytest.fixture
def api_client(backend_module):
    return TestClient(backend_module.app)


class TestBackendAPI:
    def test_health_endpoint_schema(self, api_client: TestClient):
        response = api_client.get("/health")

        assert response.status_code == 200
        data = response.json()

        assert set(data.keys()) == {"status", "hedera", "stellar", "network"}
        assert data["status"] in {"healthy", "degraded"}
        assert data["hedera"] in {"connected", "not configured", "unknown", "error"}
        assert data["stellar"] in {"configured", "not configured", "unknown"}
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

        assert set(data.keys()) == expected_verify_schema_fields
        assert data["vitis_score"] == 88
        assert data["risk"] == "low"
        assert data["status"] == "ASSET_CERTIFIED"
        assert data["hedera_notarization"] == "SUCCESS (MOCK)"
        assert data["stellar_tx_hash"] == "stellar_tx_hash_mock_001"
        assert data["satellite_img"].startswith("data:image/")

    def test_certificate_endpoint_schema(self, api_client: TestClient):
        response = api_client.get("/certificate/farm-ar-001")

        assert response.status_code == 200
        data = response.json()

        assert set(data.keys()) == {
            "farm_id",
            "vitis_score",
            "timestamp",
            "hedera_txn_id",
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

        assert set(data.keys()) == {"history", "coordinates", "months_analyzed"}
        assert data["months_analyzed"] == 6
        assert data["coordinates"] == {"lat": -33.1234, "lon": -68.9876}
        assert isinstance(data["history"], list)
        assert len(data["history"]) == 6

        for item in data["history"]:
            assert set(item.keys()) == {"date", "ndvi", "status"}
            assert isinstance(item["date"], str)
            assert isinstance(item["ndvi"], float)
            assert item["status"] in {"healthy", "moderate", "stressed"}