# backend/stellar_adapter.py
"""
Stellar/Soroban Adapter - Asset Layer

Este módulo maneja la interacción con el contrato Soroban en Stellar
para almacenar y actualizar los VitisScores de los viñedos.

Arquitectura:
- Trust Layer: Hedera HCS (ya existente en protocol_agent.py)
- Asset Layer: Stellar Soroban (este archivo)
"""

import os
import logging
import time
import asyncio
from typing import Any, Optional
from dataclasses import dataclass
from enum import Enum

from stellar_sdk import (
    Address,
    Keypair,
    Network,
    SorobanServer,
    TransactionBuilder,
    InvokeHostFunction,
    ExtendFootprintTtl,
    FootprintPermission,
    xdr as stellar_xdr,
)
from stellar_sdk.soroban_rpc import GetTransactionStatus

logger = logging.getLogger("vitistrust.stellar")


class StellarNetwork(Enum):
    """Redes disponibles."""
    TESTNET = "testnet"
    MAINNET = "mainnet"
    FUTURENET = "futurenet"


@dataclass
class SorobanConfig:
    """Configuración para Soroban."""
    network: StellarNetwork
    rpc_url: str
    network_passphrase: str
    oracle_keypair: Keypair  # Clave del oráculo (admin del contrato)
    contract_id: str        # Dirección del contrato desplegado


@dataclass
class SorobanMetrics:
    """Métricas operativas básicas del adapter."""
    total_submissions: int = 0
    retry_attempts: int = 0
    sequence_collisions: int = 0
    idempotency_hits: int = 0


class SorobanAdapter:
    """
    Adapter para interactuar con el contrato VitisRegistry en Soroban.
    
    Maneja:
    - Inicialización del contrato
    - Actualización de VitisScore
    - Consultas de registros
    """

    def __init__(self, config: SorobanConfig):
        self.config = config
        self.server = SorobanServer(config.rpc_url)
        self._contract_address = Address(config.contract_id)
        self._source_locks: dict[str, asyncio.Lock] = {}
        self._idempotency_cache: dict[str, tuple[str, float]] = {}
        self._inflight_idempotency: dict[str, asyncio.Future[str]] = {}
        self._idempotency_guard = asyncio.Lock()
        self._metrics = SorobanMetrics()
        self._sequence_retry_max_attempts = int(os.getenv("STELLAR_SEQUENCE_MAX_RETRIES", "4"))
        self._sequence_retry_base_delay = float(os.getenv("STELLAR_SEQUENCE_RETRY_BASE_DELAY", "0.5"))
        self._tx_poll_interval = float(os.getenv("STELLAR_TX_POLL_INTERVAL", "0.8"))
        self._tx_poll_timeout = float(os.getenv("STELLAR_TX_POLL_TIMEOUT", "45"))
        self._idempotency_window_seconds = int(os.getenv("STELLAR_IDEMPOTENCY_WINDOW_SECONDS", "60"))
        
        logger.info(f"SorobanAdapter initialized for {config.network.value}")
        logger.info(f"Contract ID: {config.contract_id}")
        logger.info(f"Oracle: {config.oracle_keypair.public_key}")

    def _get_invocation_data(
        self,
        function_name: str,
        args: list[Any]
    ) -> stellar_xdr.InvokeHostFunction:
        """Construye la invocación de función del contrato."""
        
        # Crear los argumentos XDR para la función
        host_fn_args = []
        
        for arg in args:
            if isinstance(arg, int):
                host_fn_args.append(stellar_xdr.SCVal(
                    type=stellar_xdr.SCValType.SCValTypeU32,
                    u32=stellar_xdr.U32(arg)
                ))
            elif isinstance(arg, str):
                # Convertir string a Symbol
                symbol = stellar_xdr.Symbol(arg.encode())
                host_fn_args.append(stellar_xdr.SCVal(
                    type=stellar_xdr.SCValType.SCValTypeSymbol,
                    symbol=symbol
                ))
            elif isinstance(arg, bytes):
                # BytesN<32> para transaction ID
                host_fn_args.append(stellar_xdr.SCVal(
                    type=stellar_xdr.SCValType.SCValTypeBytesN,
                    bytes_n=stellar_xdr.BytesN(bytes(arg))
                ))
            elif isinstance(arg, Address):
                host_fn_args.append(arg.to_sc_val())
        
        # Crear el invoke host function
        host_fn = stellar_xdr.InvokeHostFunction(
            function=stellar_xdr.HostFunction(
                type=stellar_xdr.HostFunctionType.HOST_FUNCTION_TYPE_INVOKE_CONTRACT,
                invoke_contract=stellar_xdr.InvokeContract(
                    contract_address=self._contract_address.to_sc_address(),
                    function=stellar_xdr.Symbol(function_name.encode()),
                    args=stellar_xdr.Tuple(host_fn_args)
                )
            )
        )
        
        return InvokeHostFunction(host_fn=host_fn)

    async def _submit_transaction(
        self,
        source: Keypair,
        operations: list[Any],
        signers: list[Keypair] | None = None
    ) -> str:
        """
        Construye, firma y envía una transacción a Soroban.
        
        Returns:
            Transaction hash
        """
        self._metrics.total_submissions += 1
        source_lock = self._source_locks.setdefault(source.public_key, asyncio.Lock())

        async with source_lock:
            last_error: Exception | None = None
            for attempt in range(1, self._sequence_retry_max_attempts + 1):
                try:
                    account = await self.server.get_account(source.public_key)

                    builder = TransactionBuilder(
                        source_account=account,
                        network_passphrase=self.config.network_passphrase,
                        base_fee=5000,  # 0.005 XLM
                    )

                    for op in operations:
                        builder.append_operation(op)

                    builder.set_timeout(300)  # 5 minutos

                    tx = builder.build()
                    tx.sign(source)

                    if signers:
                        for signer in signers:
                            tx.sign(signer)

                    response = await self.server.send_transaction(tx)
                    tx_hash = response.hash
                    tx_data = await self._wait_for_transaction(tx_hash)

                    if tx_data.status == GetTransactionStatus.SUCCESS:
                        logger.info(f"Transaction successful: {tx_hash}")
                        return tx_hash

                    error_msg = f"Transaction failed: {tx_data.status}"
                    if self._is_sequence_error(error_msg):
                        self._metrics.sequence_collisions += 1
                        raise RuntimeError(error_msg)

                    logger.error(error_msg)
                    raise RuntimeError(error_msg)
                except Exception as exc:
                    last_error = exc
                    if not self._is_sequence_error(exc) or attempt >= self._sequence_retry_max_attempts:
                        break

                    self._metrics.retry_attempts += 1
                    self._metrics.sequence_collisions += 1
                    delay = self._sequence_retry_base_delay * (2 ** (attempt - 1))
                    logger.warning(
                        "Sequence collision detected for %s (attempt %s/%s). "
                        "Refreshing account sequence and retrying in %.2fs.",
                        source.public_key,
                        attempt,
                        self._sequence_retry_max_attempts,
                        delay,
                    )
                    await asyncio.sleep(delay)

            collision_rate = self._metrics.sequence_collisions / max(self._metrics.total_submissions, 1)
            logger.warning(
                "Submission failed. retries=%s sequence_collisions=%s collision_rate=%.4f",
                self._metrics.retry_attempts,
                self._metrics.sequence_collisions,
                collision_rate,
            )
            raise RuntimeError(f"Transaction submission failed: {last_error}")

    async def _wait_for_transaction(self, tx_hash: str) -> Any:
        """Espera estado final de la tx con timeout para evitar polling infinito."""
        start = time.monotonic()
        while True:
            tx_data = await self.server.get_transaction(tx_hash)
            if tx_data.status != GetTransactionStatus.NOT_FOUND:
                return tx_data

            if time.monotonic() - start >= self._tx_poll_timeout:
                raise TimeoutError(
                    f"Transaction {tx_hash} not confirmed after "
                    f"{self._tx_poll_timeout} seconds"
                )
            await asyncio.sleep(self._tx_poll_interval)

    @staticmethod
    def _is_sequence_error(error: Exception | str) -> bool:
        """Detecta errores asociados a colisiones de secuencia."""
        msg = str(error).lower()
        markers = ("tx_bad_seq", "bad sequence", "sequence")
        return any(marker in msg for marker in markers)

    def _build_idempotency_key(self, farm_id: str) -> str:
        """Genera key por farm + ventana temporal."""
        window = int(time.time() // self._idempotency_window_seconds)
        return f"{farm_id}:{window}"

    async def _get_or_create_idempotency_future(self, key: str) -> tuple[bool, asyncio.Future[str]]:
        """Retorna si la llamada es dueña del future o debe esperar una existente."""
        now = time.time()
        async with self._idempotency_guard:
            cached = self._idempotency_cache.get(key)
            if cached and cached[1] > now:
                fut: asyncio.Future[str] = asyncio.get_running_loop().create_future()
                fut.set_result(cached[0])
                self._metrics.idempotency_hits += 1
                return False, fut

            inflight = self._inflight_idempotency.get(key)
            if inflight:
                self._metrics.idempotency_hits += 1
                return False, inflight

            fut = asyncio.get_running_loop().create_future()
            self._inflight_idempotency[key] = fut
            return True, fut

    async def update_vitis_score(
        self,
        farm_id: str,
        score: int,
        hedera_txn_id: bytes,
        evidence_cid: str = "",
    ) -> str:
        """
        Actualiza el VitisScore de un viñedo en el contrato Soroban.
        
        Args:
            farm_id: Identificador del viñedo (string)
            score: VitisScore (0-100)
            hedera_txn_id: Transaction ID de Hedera (32 bytes)
            evidence_cid: CID de evidencia en IPFS (opcional)
            
        Returns:
            Transaction hash de la transacción en Stellar
        """
        # Validaciones
        if not 0 <= score <= 100:
            raise ValueError("Score must be between 0 and 100")
        
        if len(hedera_txn_id) != 32:
            raise ValueError("Hedera transaction ID must be 32 bytes")
        
        logger.info(f"Updating VitisScore for {farm_id}: {score}")
        idempotency_key = self._build_idempotency_key(farm_id)
        is_owner, inflight_future = await self._get_or_create_idempotency_future(idempotency_key)
        if not is_owner:
            return await inflight_future
        
        try:
            # Construir invocación con evidence_cid si se proporciona
            args = [farm_id, score, hedera_txn_id]
            if evidence_cid:
                args.append(evidence_cid)
            
            invoke_op = self._get_invocation_data("update_score", args)
            
            # Firmar y enviar
            tx_hash = await self._submit_transaction(
                source=self.config.oracle_keypair,
                operations=[invoke_op]
            )
            
            # Cachear resultado para idempotency
            async with self._idempotency_guard:
                ttl = time.time() + self._idempotency_window_seconds
                self._idempotency_cache[idempotency_key] = (tx_hash, ttl)
                inflight_future.set_result(tx_hash)
                self._inflight_idempotency.pop(idempotency_key, None)
            
            logger.info(
                f"VitisScore updated. TX: {tx_hash} | retries={self._metrics.retry_attempts} | collisions={self._metrics.sequence_collisions}"
            )
            return tx_hash
        except Exception as exc:
            async with self._idempotency_guard:
                if not inflight_future.done():
                    inflight_future.set_exception(exc)
                self._inflight_idempotency.pop(idempotency_key, None)
            raise

    def get_metrics(self) -> dict[str, float]:
        """Expone métricas del adapter."""
        collision_rate = self._metrics.sequence_collisions / max(self._metrics.total_submissions, 1)
        return {
            "total_submissions": float(self._metrics.total_submissions),
            "retry_attempts": float(self._metrics.retry_attempts),
            "sequence_collisions": float(self._metrics.sequence_collisions),
            "sequence_collision_rate": collision_rate,
            "idempotency_hits": float(self._metrics.idempotency_hits),
        }

    async def get_vitis_score(self, farm_id: str) -> dict[str, Any]:
        """
        Consulta el VitisScore de un viñedo.
        
        Returns:
            Dict con score, timestamp, hedera_txn_id, evidence_cid, auditor
        """
        logger.info(f"Querying VitisScore for {farm_id}")
        
        # Para consulta, usamos simulate y read footprint
        # Esta es una implementación simplificada
        # En producción, usarías get_simulate_transaction
        
        # Por ahora, retornamos un placeholder
        # La implementación completa requiere obtener el footprint
        # del resultado de simulación
        
        raise NotImplementedError(
            "Query operations require implementation of "
            "read-only transaction simulation"
        )

    async def has_record(self, farm_id: str) -> bool:
        """Verifica si existe un registro para el viñedo."""
        # Similar a get_vitis_score, requiere simulación
        raise NotImplementedError("Use update_score for now")


# === Funciones de fábrica ===

def create_stellar_adapter() -> Optional[SorobanAdapter]:
    """
    Crea una instancia del adapter desde variables de entorno.
    
    Variables requeridas:
    - STELLAR_NETWORK: testnet | mainnet
    - STELLAR_RPC_URL: URL del RPC de Stellar
    - STELLAR_ORACLE_SECRET: Clave privada del oráculo
    - SOROBAN_CONTRACT_ID: ID del contrato desplegado
    """
    network_type = os.getenv("STELLAR_NETWORK", "testnet")
    
    # Configurar red
    if network_type == "mainnet":
        network = StellarNetwork.MAINNET
        rpc_url = "https://mainnet.stellar.org:443"
        passphrase = Network.MAINNET_NETWORK_PASSPHRASE
    else:
        network = StellarNetwork.TESTNET
        rpc_url = "https://soroban-testnet.stellar.org:443"
        passphrase = Network.TESTNET_NETWORK_PASSPHRASE
    
    # Obtener clave del oráculo
    oracle_secret = os.getenv("STELLAR_ORACLE_SECRET")
    if not oracle_secret:
        logger.warning("STELLAR_ORACLE_SECRET not set")
        return None
    
    try:
        oracle_keypair = Keypair.from_secret(oracle_secret)
    except Exception as e:
        logger.error(f"Invalid oracle secret key: {e}")
        return None
    
    # Obtener ID del contrato
    contract_id = os.getenv("SOROBAN_CONTRACT_ID")
    if not contract_id:
        logger.warning("SOROBAN_CONTRACT_ID not set")
        return None
    
    config = SorobanConfig(
        network=network,
        rpc_url=rpc_url,
        network_passphrase=passphrase,
        oracle_keypair=oracle_keypair,
        contract_id=contract_id,
    )
    
    return SorobanAdapter(config)
