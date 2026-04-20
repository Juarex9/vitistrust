import importlib
import os
import sys
import types
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import json
import asyncio
import importlib
import types

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
        mock_groq.return_value = mock_client
        
        from agents.reasoning_agent import analyze_vineyard_health
        
        sat_data = {"ndvi": 0.75}
        result = analyze_vineyard_health(sat_data)
        
        assert "score" in result
        assert "risk_level" in result


class TestBackend:
    """Tests for the backend API."""
    
    def test_health_endpoint_no_contract(self):
        """Test health endpoint when contract is not configured."""
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        
        with patch('backend.main.vitis_contract', None):
            with patch('backend.main.hedera_node', None):
                from backend.main import app
                client = TestClient(app)
                response = client.get("/health")
                
                assert response.status_code == 200
                data = response.json()
                assert "status" in data
    
    def test_health_endpoint_disconnected(self):
        """Test health endpoint when RSK is disconnected."""
        from fastapi.testclient import TestClient
        from unittest.mock import patch, MagicMock
        
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = False
        
        with patch('backend.main.vitis_contract', None):
            with patch('backend.main.hedera_node', None):
                with patch('backend.main.w3', mock_w3):
                    from backend.main import app
                    client = TestClient(app)
                    response = client.get("/health")
                    
                    assert response.status_code == 200
                    data = response.json()
                    assert data["rsk"] == "disconnected"
    
    def test_verify_endpoint_missing_params(self):
        """Test verification with missing parameters."""
        from fastapi.testclient import TestClient
        
        from backend.main import app
        client = TestClient(app)
        
        response = client.get("/verify-vineyard")
        assert response.status_code == 422
    
    def test_certificate_endpoint_not_found(self):
        """Test certificate endpoint when not found."""
        from fastapi.testclient import TestClient
        from unittest.mock import patch, MagicMock
        from web3 import Web3
        
        mock_contract = MagicMock()
        mock_contract.functions.certificates.return_value.call.return_value = (0, 0, "")
        
        test_address = Web3.to_checksum_address("0x" + "1" * 40)
        
        with patch('backend.main.vitis_contract', mock_contract):
            from backend.main import app
            client = TestClient(app)
            
            response = client.get(f"/certificate/{test_address}/1")
            assert response.status_code in [404, 500]
    
    def test_certifications_endpoint_empty(self):
        """Test certifications endpoint with no history."""
        from fastapi.testclient import TestClient
        from unittest.mock import patch, MagicMock
        from web3 import Web3
        
        mock_contract = MagicMock()
        mock_contract.functions.getCertificationIds.return_value.call.return_value = []
        
        test_address = Web3.to_checksum_address("0x" + "1" * 40)
        
        with patch('backend.main.vitis_contract', mock_contract):
            from backend.main import app
            client = TestClient(app)
            
            response = client.get(f"/certifications/{test_address}")
            assert response.status_code == 200
            data = response.json()
            assert "total_certifications" in data


class TestRetryLogic:
    """Tests for retry logic in backend."""

    @staticmethod
    def _get_retry_on_failure():
        fake_stellar_adapter = types.SimpleNamespace(
            create_stellar_adapter=lambda: None,
            SorobanAdapter=object,
        )
        with patch.dict(sys.modules, {"backend.stellar_adapter": fake_stellar_adapter}):
            backend_main = importlib.import_module("backend.main")
        return backend_main.retry_on_failure
    
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
