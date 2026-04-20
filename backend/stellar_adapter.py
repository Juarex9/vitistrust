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
        # Obtener secuencia actual
        account = await self.server.get_account(source.public_key)
        
        # Construir transacción
        builder = TransactionBuilder(
            source_account=account,
            network_passphrase=self.config.network_passphrase,
            base_fee=5000,  # 0.005 XLM
        )
        
        for op in operations:
            builder.append_operation(op)
        
        # Configurar footprint (lectura/escritura)
        # Por simplicidad, usamos footprint temporal
        builder.set_timeout(300)  # 5 minutos
        
        tx = builder.build()
        
        # Firmar con el oráculo
        tx.sign(source)
        
        # Firmar con signers adicionales si existen
        if signers:
            for signer in signers:
                tx.sign(signer)
        
        # Enviar a la red
        response = await self.server.send_transaction(tx)
        
        # Esperar confirmación
        tx_hash = response.hash
        
        while True:
            tx_data = await self.server.get_transaction(tx_hash)
            if tx_data.status != GetTransactionStatus.NOT_FOUND:
                break
        
        if tx_data.status == GetTransactionStatus.SUCCESS:
            logger.info(f"Transaction successful: {tx_hash}")
            return tx_hash
        else:
            error_msg = f"Transaction failed: {tx_data.status}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

    async def update_vitis_score(
        self,
        farm_id: str,
        score: int,
        hedera_txn_id: bytes,
    ) -> str:
        """
        Actualiza el VitisScore de un viñedo en el contrato Soroban.
        
        Args:
            farm_id: Identificador del viñedo (string)
            score: VitisScore (0-100)
            hedera_txn_id: Transaction ID de Hedera (32 bytes)
            
        Returns:
            Transaction hash de la transacción en Stellar
        """
        # Validaciones
        if not 0 <= score <= 100:
            raise ValueError("Score must be between 0 and 100")
        
        if len(hedera_txn_id) != 32:
            raise ValueError("Hedera transaction ID must be 32 bytes")
        
        logger.info(f"Updating VitisScore for {farm_id}: {score}")
        
        # Construir invocación
        invoke_op = self._get_invocation_data(
            "update_score",
            [
                farm_id,
                score,
                hedera_txn_id
            ]
        )
        
        # Firmar y enviar (el oráculo es el admin, firma la tx)
        tx_hash = await self._submit_transaction(
            source=self.config.oracle_keypair,
            operations=[invoke_op]
        )
        
        logger.info(f"VitisScore updated successfully. TX: {tx_hash}")
        return tx_hash

    async def get_vitis_score(self, farm_id: str) -> dict[str, Any]:
        """
        Consulta el VitisScore de un viñedo.
        
        Returns:
            Dict con score, timestamp, hedera_txn_id, auditor
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
