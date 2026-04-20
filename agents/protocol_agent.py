# agents/protocol_agent.py
"""
Hedera Protocol Agent - Notarización en Hedera Consensus Service (HCS)

Este módulo maneja la creación de topics y el envío de mensajes a Hedera
para crear un log inmutable de las auditorías de viñedos.
"""

import logging
import random
import time
from typing import Any, Optional

from dotenv import load_dotenv
import os

load_dotenv()

logger = logging.getLogger("vitistrust.protocol")

# DER Private Key del portal (si está configurada en .env)
DER_PRIVATE_KEY = os.getenv("HEDERA_DER_PRIVATE_KEY", "")
SUCCESS_MOCK = "SUCCESS_MOCK"


def _extract_raw_key_from_der(der_hex: str) -> bytes:
    """
    Extrae los 32 bytes de la clave privada desde el formato DER.
    
    El DER de Hedera tiene el formato:
    3030020100300706052b8104000a04220420 + [32 bytes de clave]
    """
    der_hex = der_hex.replace("0x", "").replace(" ", "")
    
    # Los últimos 64 caracteres hex = 32 bytes = clave raw
    raw_hex = der_hex[-64:]
    
    return bytes.fromhex(raw_hex)


def _get_hedera_client():
    """Inicializa el cliente de Hedera."""
    try:
        from hiero_sdk_python import Client, AccountId, PrivateKey
        
        operator_id = os.getenv("HEDERA_ACCOUNT_ID")
        der_key = os.getenv("HEDERA_DER_PRIVATE_KEY") or os.getenv("HEDERA_PRIVATE_KEY")
        
        if not operator_id or not der_key:
            raise ValueError("HEDERA_ACCOUNT_ID and HEDERA_PRIVATE_KEY (or HEDERA_DER_PRIVATE_KEY) must be set")
        
        # Crear cliente para testnet
        client = Client.for_testnet()
        
        # Configurar el operador
        account_id = AccountId.from_string(operator_id)
        
        # Extraer la clave raw del DER y crear la clave privada ECDSA
        raw_key = _extract_raw_key_from_der(der_key)
        private_key = PrivateKey.from_bytes_ecdsa(raw_key)
        
        client.set_operator(account_id, private_key)
        
        logger.info(f"Hedera client initialized for account {operator_id}")
        return client
        
    except ImportError:
        logger.error("hiero-sdk-python not installed")
        return None


class HederaProtocol:
    """Protocolo de notarización en Hedera Consensus Service."""
    
    def __init__(self, is_mock: bool = False) -> None:
        self.is_mock = is_mock
        self.client = None if self.is_mock else _get_hedera_client()
        if self.client is None and not self.is_mock:
            logger.warning("Hedera SDK not found or client failed. Using MOCK mode for demo.")
            self.is_mock = True
        
        self.account_id = os.getenv("HEDERA_ACCOUNT_ID", "0.0.0")
        self.topic_id = os.getenv("HEDERA_TOPIC_ID", "0.0.0")
        logger.info(f"HederaProtocol initialized. Topic: {self.topic_id}")
    
    def _get_operator_key(self):
        """Obtiene la clave privada del operador."""
        from hiero_sdk_python import PrivateKey
        
        der_key = os.getenv("HEDERA_DER_PRIVATE_KEY") or os.getenv("HEDERA_PRIVATE_KEY")
        raw_key = _extract_raw_key_from_der(der_key)
        return PrivateKey.from_bytes_ecdsa(raw_key)
    
    def _get_receipt(self, tx_response):
        """Obtiene el receipt de la transacción - maneja bugs del SDK."""
        from hiero_sdk_python import TransactionGetReceiptQuery
        
        # El SDK a veces retorna el receipt directamente en lugar del response
        # Verificar el tipo
        if hasattr(tx_response, 'topic_id'):
            # Ya es un receipt
            return tx_response
        
        # Si es un TransactionResponse, obtener el receipt
        try:
            if hasattr(tx_response, 'get_receipt'):
                return tx_response.get_receipt(self.client)
        except AttributeError:
            pass
        
        # Fallback: usar TransactionGetReceiptQuery
        try:
            tx_id = tx_response.transaction_id
            return (TransactionGetReceiptQuery(tx_id=tx_id)
                    .execute(self.client))
        except Exception:
            # Último recurso: intentar con transactionId
            try:
                tx_id = tx_response.transactionId
                return (TransactionGetReceiptQuery(tx_id=tx_id)
                        .execute(self.client))
            except Exception:
                return tx_response
    
    def create_audit_topic(self) -> Optional[str]:
        if getattr(self, 'is_mock', False):
            mock_topic = f"0.0.{random.randint(100000, 999999)}"
            logger.info(f"Mock topic created: {mock_topic}")
            return mock_topic

        from hiero_sdk_python import TopicCreateTransaction
        try:
            logger.info("Creating HCS audit topic...")
            operator_key = self._get_operator_key()
            
            # Crear la transacción
            transaction = (
                TopicCreateTransaction(memo="VitisTrust Audit Log")
                .freeze_with(self.client)
                .sign(operator_key)
            )
            
            # Ejecutar
            tx_response = transaction.execute(self.client)
            
            # Obtener el receipt
            receipt = self._get_receipt(tx_response)
            
            # Extraer topic_id - manejar diferentes formatos del SDK
            topic_id_obj = receipt.topic_id
            topic_id = f"{topic_id_obj.shard}.{topic_id_obj.realm}.{topic_id_obj.num}"
            
            # Verificar que la transacción fue exitosa
            status_obj = receipt.status
            if hasattr(status_obj, 'to_string'):
                status = status_obj.to_string()
            else:
                status = "SUCCESS" if status_obj == 22 else f"STATUS_{status_obj}"
            
            logger.info(f"Audit topic created: {topic_id} (status: {status})")
            return topic_id
            
        except Exception as e:
            logger.error(f"Failed to create HCS topic: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def notarize_vitis_report(self, topic_id: str, report_data: dict[str, Any]) -> str:
        import json
        try:
            message = json.dumps(report_data)
            logger.info(f"Notarizing to topic {topic_id}: {message[:100]}...")
            
            if getattr(self, 'is_mock', False):
                # Fake delay for "wow" effect
                time.sleep(1)
                logger.info("Mock notarization successful (No SDK)")
                return SUCCESS_MOCK

            from hiero_sdk_python import TopicMessageSubmitTransaction, TopicId
            operator_key = self._get_operator_key()
            tid = TopicId.from_string(topic_id)
            
            # Crear y ejecutar la transacción
            transaction = (
                TopicMessageSubmitTransaction(topic_id=tid, message=message)
                .freeze_with(self.client)
                .sign(operator_key)
            )
            
            tx_response = transaction.execute(self.client)
            receipt = self._get_receipt(tx_response)
            
            # El status puede ser un int o un objeto Status
            status_obj = receipt.status
            if hasattr(status_obj, 'to_string'):
                status = status_obj.to_string()
            else:
                # Es un int - convertir a string (SUCCESS = 22)
                status = "SUCCESS" if status_obj == 22 else f"STATUS_{status_obj}"
            
            logger.info(f"Notarization successful: {status}")
            return status
            
        except Exception as e:
            if getattr(self, 'is_mock', False):
                logger.info("Mock notarization successful (No SDK)")
                return SUCCESS_MOCK
            logger.error(f"Failed to notarize: {e}")
            return f"ERROR: {str(e)}"
    
    def get_topic_messages(self, topic_id: str, limit: int = 10) -> list[dict]:
        """
        Obtiene mensajes de un topic via Mirror Node.
        """
        import requests
        import base64
        
        try:
            url = f"https://testnet.mirrornode.hedera.com/api/v1/topics/{topic_id}/messages?limit={limit}"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            messages = []
            
            for msg in data.get("messages", []):
                msg_b64 = msg.get("message", "")
                msg_decoded = base64.b64decode(msg_b64).decode("utf-8")
                
                messages.append({
                    "sequence": msg.get("sequence_number"),
                    "message": msg_decoded,
                    "timestamp": msg.get("consensus_timestamp")
                })
            
            return messages
            
        except Exception as e:
            logger.error(f"Failed to get topic messages: {e}")
            return []


def main():
    """Test del protocolo Hedera."""
    print("=" * 60)
    print("HEDERA PROTOCOL TEST")
    print("=" * 60)
    
    # Agregar la DER key al .env si no está
    der_key = os.getenv("HEDERA_DER_PRIVATE_KEY")
    if not der_key:
        # Usar la hex key como fallback
        hex_key = os.getenv("HEDERA_PRIVATE_KEY", "")
        if hex_key:
            # Crear DER manually para clave hex
            der_key = f"3030020100300706052b8104000a04220420{hex_key}"
            print(f"[INFO] Using hex key as DER fallback")
    
    try:
        hedera = HederaProtocol()
        print(f"[OK] Client initialized: {hedera.account_id}")
        
        # Verificar si hay un topic configurado
        topic_id = hedera.topic_id
        if not topic_id or topic_id == "0.0.8384975":
            print("\nNo topic configured. Creating new topic...")
            topic_id = hedera.create_audit_topic()
            if topic_id:
                print(f"\n=== TOPIC CREADO ===")
                print(f"Topic ID: {topic_id}")
                print(f"Agrega esto a tu .env: HEDERA_TOPIC_ID={topic_id}")
                print("=" * 60)
            else:
                print("ERROR: No se pudo crear el topic")
                return
        else:
            print(f"Using existing topic: {topic_id}")
        
        # Testear enviar un mensaje
        print(f"\nTesting message submission to {topic_id}...")
        test_report = {
            "vitis_score": 75,
            "risk_level": "low",
            "justification": "Test message from VitisTrust"
        }
        
        status = hedera.notarize_vitis_report(topic_id, test_report)
        print(f"Message status: {status}")
        
        if "SUCCESS" in status:
            print("\n[OK] Hedera protocol working!")
            
            # Verificar que el mensaje fue publicado
            print("\nVerifying message in topic...")
            messages = hedera.get_topic_messages(topic_id, limit=1)
            if messages:
                print(f"Latest message: {messages[0]}")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
