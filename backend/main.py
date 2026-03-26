import os
import logging
import asyncio
from typing import Any
from functools import wraps

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

from agents.perception_agent import get_real_ndvi
from agents.reasoning_agent import analyze_vineyard_health
from agents.protocol_agent import HederaProtocol
from backend.constants import VITIS_ABI
from web3 import Web3
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("vitistrust")

app = FastAPI(title="VitisTrust Oracle API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_RETRIES = 3
RETRY_DELAYS = [1, 2, 5]

def retry_on_failure(max_retries: int = MAX_RETRIES, delays: list = RETRY_DELAYS):
    """Decorator para reintentar funciones que pueden fallar."""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        delay = delays[attempt]
                        logger.warning(f"{func.__name__} failed (attempt {attempt + 1}/{max_retries}), retrying in {delay}s: {e}")
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"{func.__name__} failed after {max_retries} attempts: {e}")
            raise last_error
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        delay = delays[attempt]
                        logger.warning(f"{func.__name__} failed (attempt {attempt + 1}/{max_retries}), retrying in {delay}s: {e}")
                        import time
                        time.sleep(delay)
                    else:
                        logger.error(f"{func.__name__} failed after {max_retries} attempts: {e}")
            raise last_error
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator

RSK_RPC_URL = os.getenv("RSK_RPC_URL")
RSK_ORACLE_ADDRESS = os.getenv("RSK_ORACLE_ADDRESS")
RSK_PRIVATE_KEY = os.getenv("RSK_PRIVATE_KEY")
RSK_CONTRACT_ADDRESS = os.getenv("RSK_CONTRACT_ADDRESS")

w3 = Web3(Web3.HTTPProvider(RSK_RPC_URL))

if not RSK_CONTRACT_ADDRESS:
    logger.warning("RSK_CONTRACT_ADDRESS not set - contract calls will fail")

vitis_contract = w3.eth.contract(address=RSK_CONTRACT_ADDRESS, abi=VITIS_ABI) if RSK_CONTRACT_ADDRESS else None

hedera_node = None
try:
    hedera_node = HederaProtocol()
except Exception as e:
    logger.error(f"Failed to initialize Hedera: {e}")

retry_decorator = retry_on_failure()

@retry_decorator
async def retry_satellite(lat: float, lon: float) -> dict[str, Any]:
    """Retry wrapper for satellite API calls."""
    return get_real_ndvi(lat, lon)

@retry_decorator
async def retry_ai_analysis(sat_data: dict[str, Any]) -> dict[str, Any]:
    """Retry wrapper for AI analysis."""
    return analyze_vineyard_health(sat_data)

@retry_decorator  
async def retry_hedera(topic_id: str, verdict: dict[str, Any]) -> str:
    """Retry wrapper for Hedera notarization."""
    return hedera_node.notarize_vitis_report(topic_id, verdict)


class VerifyRequest(BaseModel):
    lat: float
    lon: float
    asset_address: str
    token_id: int


@app.get("/health")
async def health_check() -> dict[str, Any]:
    """Verifica el estado de las conexiones a RSK y Hedera."""
    health = {"status": "healthy", "rsk": "unknown", "hedera": "unknown"}
    
    if w3.is_connected():
        health["rsk"] = "connected"
    else:
        health["rsk"] = "disconnected"
        health["status"] = "degraded"
    
    try:
        if hedera_node is not None and hedera_node.client is not None:
            health["hedera"] = "connected"
        else:
            health["hedera"] = "not configured"
    except Exception:
        health["hedera"] = "error"
        health["status"] = "degraded"
    
    return health


@app.get("/verify-vineyard")
async def verify(lat: float, lon: float, asset_address: str, token_id: int) -> dict[str, Any]:
    """
    Audita un viñedo tokenizado.
    
    Flujo:
    1. Consulta datos satelitales (NDVI)
    2. Analiza con IA (DeepSeek-R1)
    3. Notariza en Hedera (HCS)
    4. Certifica en Rootstock (VitisRegistry)
    """
    # Normalize address to lowercase
    asset_address = asset_address.lower()
    
    logger.info(f"Starting audit for asset {asset_address} token {token_id}")
    
    try:
        if not vitis_contract:
            raise HTTPException(status_code=503, detail="Contract not configured")
        
        logger.info(f"🛰️ Consulting satellite for {lat}, {lon}")
        sat_data = await retry_satellite(lat, lon)
        if sat_data["status"] == "error":
            logger.error(f"Satellite error: {sat_data['message']}")
            raise HTTPException(status_code=400, detail=sat_data["message"])

        logger.info("🧠 AI analyzing vineyard health")
        verdict = await retry_ai_analysis(sat_data)

        logger.info("🛡️ Notarizing in Hedera")
        topic_id = os.getenv("HEDERA_TOPIC_ID")
        if not topic_id:
            raise HTTPException(status_code=500, detail="HEDERA_TOPIC_ID not configured")
        if not hedera_node:
            raise HTTPException(status_code=503, detail="Hedera not configured")
        hedera_status = await retry_hedera(topic_id, verdict)

        logger.info("🔗 Signing certification in Rootstock")
        nonce = w3.eth.get_transaction_count(RSK_ORACLE_ADDRESS)
        
        txn = vitis_contract.functions.certifyAsset(
            Web3.to_checksum_address(asset_address),
            token_id,
            int(verdict["score"]),
            topic_id
        ).build_transaction({
            "chainId": 31,
            "gas": 200000,
            "gasPrice": w3.eth.gas_price,
            "from": RSK_ORACLE_ADDRESS,
            "nonce": nonce,
        })

        signed_txn = w3.eth.account.sign_transaction(txn, private_key=RSK_PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
        
        logger.info(f"✅ Audit complete. TX: {tx_hash.hex()}")
        
        return {
            "vitis_score": verdict["score"],
            "risk": verdict["risk_level"],
            "justification": verdict["justification"],
            "hedera_notarization": hedera_status,
            "rsk_tx_hash": tx_hash.hex(),
            "status": "ASSET_CERTIFIED"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Audit failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/certificate/{asset_address}/{token_id}")
async def get_certificate(asset_address: str, token_id: int) -> dict[str, Any]:
    """Consulta una certificación previa del contrato en RSK."""
    try:
        if not vitis_contract:
            raise HTTPException(status_code=503, detail="Contract not configured")
        
        # Normalizar address a lowercase checksum
        normalized_address = Web3.to_checksum_address(asset_address.lower())
        logger.info(f"Querying certificate for {normalized_address} token {token_id}")
        
        cert = vitis_contract.functions.certificates(
            normalized_address,
            token_id
        ).call()
        
        logger.info(f"Raw certificate data: {cert}")
        
        # Verificar si hay datos válidos (score > 0 indica que existe)
        vitis_score = cert[0]
        timestamp = cert[1]
        topic_id = cert[2]
        
        if vitis_score == 0 and timestamp == 0 and not topic_id:
            raise HTTPException(status_code=404, detail="No certificate found for this asset")
        
        return {
            "asset_address": normalized_address,
            "token_id": token_id,
            "vitis_score": vitis_score,
            "timestamp": timestamp,
            "hedera_topic_id": topic_id
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Certificate query failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/certifications/{asset_address}")
async def get_certification_history(asset_address: str) -> dict[str, Any]:
    """Consulta el historial de certificaciones para un activo."""
    try:
        if not vitis_contract:
            raise HTTPException(status_code=503, detail="Contract not configured")
        
        normalized_address = Web3.to_checksum_address(asset_address.lower())
        logger.info(f"Querying certification history for {normalized_address}")
        
        try:
            token_ids = vitis_contract.functions.getCertificationIds(normalized_address).call()
        except Exception:
            token_ids = []
        
        certifications = []
        for token_id in token_ids:
            try:
                cert = vitis_contract.functions.certificates(normalized_address, token_id).call()
                if cert[0] > 0 or cert[1] > 0:
                    certifications.append({
                        "token_id": token_id,
                        "vitis_score": cert[0],
                        "timestamp": cert[1],
                        "hedera_topic_id": cert[2]
                    })
            except Exception:
                continue
        
        return {
            "asset_address": normalized_address,
            "total_certifications": len(certifications),
            "certifications": certifications
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Certification history query failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)