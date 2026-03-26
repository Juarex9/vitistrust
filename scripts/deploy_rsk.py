"""
Script para desplegar VitisRegistry.sol a Rootstock Testnet.

Uso:
    python scripts/deploy_rsk.py

El script compila el contrato y lo despliega a RSK testnet.
Requiere tener RSK_PRIVATE_KEY configurada en .env
"""

import os
import sys
from dotenv import load_dotenv
from web3 import Web3

load_dotenv()


def compile_contract():
    """Compila el contrato Solidity usando solc."""
    try:
        import solcx
    except ImportError:
        print("ERROR: solcx not installed. Install with: pip install solc")
        print("Or use Foundry instead: forge create ...")
        sys.exit(1)
    
    solcx.install_solc("0.8.20")
    
    contract_path = os.path.join(os.path.dirname(__file__), "..", "contracts", "VitisRegistry.sol")
    
    with open(contract_path, "r") as f:
        source = f.read()
    
    compiled = solcx.compile_source(
        source,
        solc_version="0.8.20",
        output_values=["abi", "bin"]
    )
    
    contract_id = list(compiled.keys())[0]
    return compiled[contract_id]["abi"], compiled[contract_id]["bin"]


def deploy():
    """Despliega el contrato a RSK Testnet."""
    rpc_url = os.getenv("RSK_RPC_URL")
    private_key = os.getenv("RSK_PRIVATE_KEY")
    
    if not rpc_url or not private_key:
        print("ERROR: RSK_RPC_URL and RSK_PRIVATE_KEY must be set in .env")
        sys.exit(1)
    
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    
    if not w3.is_connected():
        print("ERROR: Cannot connect to RSK network")
        sys.exit(1)
    
    print(f"[*] Connected to RSK: chain_id={w3.eth.chain_id}")
    
    account = w3.eth.account.from_key(private_key)
    print(f"[*] Deploying from: {account.address}")
    
    balance = w3.eth.get_balance(account.address)
    print(f"[*] Balance: {w3.from_wei(balance, 'ether')} tRBTC")
    
    if balance == 0:
        print("WARNING: Account has no balance. Get testnet tRBTC from faucet.")
    
    print("[*] Compiling contract...")
    abi, bytecode = compile_contract()
    
    print("[*] Deploying VitisRegistry.sol...")
    
    Contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    tx_hash = Contract.constructor().build_transaction({
        "chainId": 31,
        "gasPrice": w3.eth.gas_price,
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
    })
    
    signed = w3.eth.account.sign_transaction(tx_hash, private_key=private_key)
    tx = w3.eth.send_raw_transaction(signed.raw_transaction)
    
    print(f"[*] Transaction sent: {tx.hex()}")
    print("[*] Waiting for confirmation...")
    
    receipt = w3.eth.wait_for_transaction_receipt(tx)
    
    if receipt.status == 1:
        print("\n" + "="*50)
        print("CONTRACT DEPLOYED SUCCESSFULLY!")
        print("="*50)
        print(f"Contract Address: {receipt.contractAddress}")
        print(f"Transaction Hash: {receipt.transactionHash.hex()}")
        print(f"Gas Used: {receipt.gasUsed}")
        print("\nAdd this to your .env:")
        print(f"RSK_CONTRACT_ADDRESS={receipt.contractAddress}")
        print("="*50)
        
        return receipt.contractAddress
    else:
        print("ERROR: Deployment failed!")
        sys.exit(1)


if __name__ == "__main__":
    deploy()
