# backend/stellar_adapter.py
"""
Stellar/Soroban Adapter - Asset Layer

Este módulo maneja la interacción con el contrato Soroban en Stellar
para almacenar y actualizar los VitisScores de los viñedos.

Nota: Versión simplificada para API stellar-sdk 13.x
"""

import os
import logging
import time
import asyncio
import subprocess
import json
from typing import Any, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger("vitistrust.stellar")


class StellarNetwork(Enum):
    TESTNET = "testnet"
    MAINNET = "mainnet"


@dataclass
class SorobanConfig:
    network: StellarNetwork
    rpc_url: str
    network_passphrase: str
    oracle_secret: str
    contract_id: str


@dataclass
class SorobanMetrics:
    total_submissions: int = 0
    retry_attempts: int = 0
    sequence_collisions: int = 0
    idempotency_hits: int = 0


class SorobanAdapter:
    """
    Adapter para interactuar con el contrato VitisRegistry en Soroban.
    Versión simplificada - stub que permite el funcionamiento del backend.
    """
    
    def __init__(self, config: SorobanConfig):
        self.config = config
        self._metrics = SorobanMetrics()
        self._idempotency_cache: dict[str, tuple[str, float]] = {}
        self._idempotency_window_seconds = 60
        
        logger.info(f"SorobanAdapter initialized for {config.network.value}")
        logger.info(f"Contract ID: {config.contract_id}")
        
        # Verificar si stellar_sdk está disponible
        self._stellar_available = False
        try:
            from stellar_sdk import (
                Keypair,
                Network,
                SorobanServer,
                TransactionBuilder,
            )
            self._Keypair = Keypair
            self._Network = Network
            self._SorobanServer = SorobanServer
            self._TransactionBuilder = TransactionBuilder
            self._stellar_available = True
            logger.info("Stellar SDK available - full adapter mode")
        except ImportError as e:
            logger.warning(f"Stellar SDK not available: {e}")
            logger.info("Running in stub mode - transactions will be mocked")

    def get_metrics(self) -> dict[str, float]:
        collision_rate = self._metrics.sequence_collisions / max(self._metrics.total_submissions, 1)
        return {
            "total_submissions": float(self._metrics.total_submissions),
            "retry_attempts": float(self._metrics.retry_attempts),
            "sequence_collisions": float(self._metrics.sequence_collisions),
            "sequence_collision_rate": collision_rate,
            "idempotency_hits": float(self._metrics.idempotency_hits),
        }

    def _build_idempotency_key(self, farm_id: str) -> str:
        window = int(time.time() // self._idempotency_window_seconds)
        return f"{farm_id}:{window}"

    async def update_vitis_score(
        self,
        farm_id: str,
        score: int,
        hedera_txn_id: bytes,
        evidence_cid: str = "",
    ) -> str:
        """
        Actualiza el VitisScore de un viñedo en el contrato Soroban.
        
        Returns:
            Transaction hash
        """
        if not 0 <= score <= 100:
            raise ValueError("Score must be between 0 and 100")
        
        if len(hedera_txn_id) != 32:
            raise ValueError("Hedera transaction ID must be 32 bytes")
        
        logger.info(f"Updating VitisScore for {farm_id}: {score}")
        
        # Verificar idempotency
        idempotency_key = self._build_idempotency_key(farm_id)
        if idempotency_key in self._idempotency_cache:
            cached_hash, ttl = self._idempotency_cache[idempotency_key]
            if time.time() < ttl:
                self._metrics.idempotency_hits += 1
                logger.info(f"Idempotency hit, returning cached: {cached_hash}")
                return cached_hash
        
        self._metrics.total_submissions += 1
        
        # Por ahora, usar stub mode (WSL tiene problemas de config)
        # TODO: habilitar cuando WSL esteja bien configurado
        logger.warning("Using stub mode - WSL not properly configured")
        mock_hash = f"stub_tx_{farm_id}_{int(time.time())}"
        
        # Cachear resultado
        ttl = time.time() + self._idempotency_window_seconds
        self._idempotency_cache[idempotency_key] = (mock_hash, ttl)
        
        logger.info(f"VitisScore updated (stub mode). TX: {mock_hash}")
        return mock_hash
    
    async def get_vitis_score(self, farm_id: str) -> dict[str, Any]:
        """Consulta el VitisScore de un viñedo."""
        logger.info(f"Querying VitisScore for {farm_id} (stub)")
        
        raise NotImplementedError("Query operations not yet implemented")

    async def has_record(self, farm_id: str) -> bool:
        """Verifica si existe un registro."""
        raise NotImplementedError("Use update_score for now")

    async def register_location(
        self,
        farm_id: str,
        lat: float,
        lon: float,
        geohash: str = "",
    ) -> str:
        """
        Registra la ubicación de un viñedo en el contrato Soroban.
        
        Args:
            farm_id: Identificador del viñedo
            lat: Latitud
            lon: Longitud
            geohash: Geohash opcional
            
        Returns:
            Transaction hash
        """
        # Convertir a integers multiplicando por 10^6
        lat_i128 = int(lat * 1_000_000)
        lon_i128 = int(lon * 1_000_000)
        
        logger.info(f"Registering location for {farm_id}: lat={lat}, lon={lon}, geohash={geohash}")
        
        # En modo stub, retornar hash mock
        mock_hash = f"mock_location_{farm_id}_{int(time.time())}"
        return mock_hash

    async def has_location(self, farm_id: str) -> bool:
        """Verifica si existe una ubicación registrada."""
        raise NotImplementedError("Query operations not yet implemented")


def create_stellar_adapter() -> Optional[SorobanAdapter]:
    """
    Crea una instancia del adapter desde variables de entorno.
    """
    network_type = os.getenv("STELLAR_NETWORK", "testnet")
    
    if network_type == "mainnet":
        network = StellarNetwork.MAINNET
        rpc_url = "https://mainnet.stellar.org:443"
        passphrase = "Public Global Stellar Network ; September 2015"
    else:
        network = StellarNetwork.TESTNET
        rpc_url = "https://soroban-testnet.stellar.org:443"
        passphrase = "Test SDF Network ; September 2015"
    
    oracle_secret = os.getenv("STELLAR_ORACLE_SECRET")
    if not oracle_secret:
        logger.warning("STELLAR_ORACLE_SECRET not set - running in stub mode")
        # Still create adapter in stub mode if contract ID is set
        contract_id = os.getenv("SOROBAN_CONTRACT_ID", "stub_contract")
        config = SorobanConfig(
            network=network,
            rpc_url=rpc_url,
            network_passphrase=passphrase,
            oracle_secret="",
            contract_id=contract_id,
        )
        return SorobanAdapter(config)
    
    contract_id = os.getenv("SOROBAN_CONTRACT_ID")
    if not contract_id:
        logger.warning("SOROBAN_CONTRACT_ID not set - running in stub mode")
        contract_id = "stub_contract"
    
    config = SorobanConfig(
        network=network,
        rpc_url=rpc_url,
        network_passphrase=passphrase,
        oracle_secret=oracle_secret,
        contract_id=contract_id,
    )
    
    return SorobanAdapter(config)