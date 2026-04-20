import pytest
from unittest.mock import patch, MagicMock
import json
import asyncio
import importlib
import types

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestPerceptionAgent:
    """Tests for the perception agent (satellite data)."""
    
    @patch.dict(os.environ, {"PLANET_API_KEY": ""})
    def test_get_real_ndvi_no_api_key(self):
        """Test error when no API key is configured."""
        from agents.perception_agent import get_real_ndvi
        result = get_real_ndvi(40.4123, -3.6912)
        
        assert result["status"] == "error"
        assert "not configured" in result["message"]


class TestReasoningAgent:
    """Tests for the reasoning agent (AI analysis)."""
    
    @patch.dict(os.environ, {"AI_API_KEY": ""})
    def test_analyze_vineyard_health_no_api_key(self):
        """Test error when no API key is configured."""
        from agents.reasoning_agent import analyze_vineyard_health
        
        sat_data = {"ndvi": 0.75}
        result = analyze_vineyard_health(sat_data)
        
        assert result["score"] == 0
        assert "risk_level" in result
    
    @patch.dict(os.environ, {"AI_API_KEY": "test_key"})
    @patch('agents.reasoning_agent.Groq')
    def test_analyze_vineyard_health_api_error(self, mock_groq):
        """Test handling of API errors."""
        mock_groq.side_effect = Exception("API Error")
        
        from agents.reasoning_agent import analyze_vineyard_health
        
        sat_data = {"ndvi": 0.75}
        result = analyze_vineyard_health(sat_data)
        
        assert "score" in result
        assert "risk_level" in result
    
    @patch.dict(os.environ, {"AI_API_KEY": "test_key"})
    @patch('agents.reasoning_agent.Groq')
    def test_analyze_vineyard_health_invalid_response(self, mock_groq):
        """Test handling of invalid AI response."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(
                message=MagicMock(content="invalid json")
            )]
        )
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
