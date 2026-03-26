# VitisTrust Development Guide

## Project Overview

VitisTrust is an Oracle Verification system for vineyard NFT verification. It uses
satellite data and AI to assess vineyard health and records certifications on Hedera
and Rootstock networks.

## Project Structure

```
vitistrust/
├── agents/                    # AI Agents
│   ├── protocol_agent.py     # Hedera HCS notarization
│   ├── perception_agent.py   # Satellite data (Sentinel-2)
│   └── reasoning_agent.py    # AI analysis (DeepSeek-R1)
├── backend/
│   ├── main.py               # FastAPI application
│   └── constants.py          # Contract ABIs
├── scripts/
│   └── deploy_rsk.py         # Deploy contract to RSK
├── contracts/
│   └── VitisRegistry.sol     # Solidity smart contract
├── requirements.txt          # Python dependencies
└── .env                      # Environment variables
```

---

## Build & Run Commands

### Python Environment

```bash
# Activate virtual environment (Windows)
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run backend server
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### Testing

```bash
# Run all tests
pytest

# Run single test file
pytest tests/test_file.py

# Run single test function
pytest tests/test_file.py::test_function_name

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=. --cov-report=html
```

### Linting & Type Checking

```bash
# Run ruff linter
ruff check .

# Run ruff with auto-fix
ruff check --fix .

# Run mypy type checker
mypy .

# Run black formatter check
black --check .

# Run isort import sorting
isort --check-only .
```

### Smart Contract (Foundry)

```bash
# Install dependencies
forge install

# Compile contracts
forge build

# Run contract tests
forge test

# Deploy to testnet
forge create --rpc-url $RSK_RPC_URL --private-key $RSK_PRIVATE_KEY --verify contracts/VitisRegistry.sol:VitisRegistry

# Deploy to mainnet
forge create --rpc-url $RSK_MAINNET_RPC --private-key $RSK_PRIVATE_KEY contracts/VitisRegistry.sol:VitisRegistry
```

---

## Code Style Guidelines

### Python (PEP 8 + Project Conventions)

#### Imports

- Use absolute imports: `from agents.perception_agent import get_vineyard_data`
- Group imports: standard library, third-party, local
- Sort alphabetically within groups

```python
# Correct
import asyncio
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException
from web3 import Web3

from agents.perception_agent import get_vineyard_data
```

#### Formatting

- Line length: 100 characters max
- Use Black for formatting
- Use 4 spaces for indentation (no tabs)

```python
# Use trailing commas for multi-line calls
result = some_function(
    arg1="value1",
    arg2="value2",
)
```

#### Types

- Use type hints for all function signatures
- Prefer `Union[X, Y]` over `Optional[X]` for multiple types
- Use concrete types (list, dict) not typing.List, typing.Dict

```python
# Correct
def get_vineyard_data(coordinates: tuple[float, float]) -> dict[str, Any]:
    """Fetch satellite data for coordinates."""
    pass


def process_scores(scores: list[int]) -> int:
    return sum(scores)


# Avoid
def get_vineyard_data(coordinates):
    pass
```

#### Naming Conventions

- Variables/functions: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Private methods: `_private_method`
- Protected attributes: `_protected_attr`

```python
class VineyardScanner:
    def __init__(self, api_key: str):
        self._api_key = api_key
        self.MAX_RETRIES = 3

    def scan_vineyard(self, contract_address: str) -> dict:
        pass
```

#### Error Handling

- Use custom exceptions for domain-specific errors
- Catch specific exceptions, never bare `except:`
- Always log errors before re-raising
- Use exception chaining with `from e`

```python
class VineyardError(Exception):
    pass


try:
    result = await fetch_data(url)
except ConnectionError as e:
    logger.error(f"Failed to connect: {e}")
    raise VineyardError(f"Connection failed: {url}") from e
except TimeoutError as e:
    logger.warning(f"Request timed out: {url}")
    raise VineyardError(f"Timeout: {url}") from e
```

#### Async/Await

- Use `async`/`await` for I/O operations
- Use `asyncio.gather()` for concurrent operations
- Avoid blocking calls in async functions

```python
async def run_audit(contract_address: str):
    coordinates, sat_data = await asyncio.gather(
        get_vineyard_coordinates(contract_address),
        get_satellite_data(coordinates),
    )
    return analyze_health(sat_data)
```

---

### Solidity (Smart Contracts)

#### Style

- Use Solidity 0.8.x+ (current: 0.8.20)
- Use NatSpec comments for public functions
- Follow naming: `CamelCase` for contracts, `snake_case` for functions

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract VitisRegistry {
    /// @notice Certifies a vineyard asset with a VitisScore
    /// @param assetContract The external NFT contract address
    /// @param tokenId The token ID
    /// @param score The VitisScore (0-100)
    /// @param topicId The Hedera topic ID for audit trail
    function certifyAsset(
        address assetContract,
        uint256 tokenId,
        uint256 score,
        string memory topicId
    ) public {
        // ...
    }
}
```

#### Security

- Use `require()` for validation
- Follow Checks-Effects-Interactions pattern
- Initialize mappings in constructor if needed
- Use specific visibility (public/private)

```solidity
require(msg.sender == oracle, "Only VitisTrust Oracle can certify");
```

---

### General Guidelines

#### Environment Variables

- Never commit secrets to version control
- Use `.env` for local development only
- Prefix test variables with appropriate network (RSK_, HEDERA_)
- Validate required env vars at startup

```python
import os
from functools import lru_cache

@lru_cache
def get_rpc_url() -> str:
    url = os.getenv("RSK_RPC_URL")
    if not url:
        raise ValueError("RSK_RPC_URL not configured")
    return url
```

#### API Design

- RESTful endpoints for FastAPI
- Use appropriate HTTP status codes
- Return structured JSON responses
- Document with OpenAPI/Swagger

```python
@app.get("/audit/{contract_address}/{token_id}")
async def run_audit(contract_address: str, token_id: int) -> dict:
    """
    Run vineyard audit for a specific NFT.

    Returns VitisScore, justification, and transaction proofs.
    """
    pass
```

#### Git

- Use conventional commits: `feat:`, `fix:`, `refactor:`, `docs:`
- Never commit `.env` or secrets
- Keep commits atomic and small
- Use meaningful commit messages

---

## Environment Configuration

Create a `.env` file with required variables:

```
# Rootstock
RSK_RPC_URL=https://public-node.testnet.rsk.co
RSK_PRIVATE_KEY=your_private_key
RSK_ORACLE_ADDRESS=your_public_address
RSK_CONTRACT_ADDRESS=0x... (after deploy)

# Hedera
HEDERA_ACCOUNT_ID=0.0.xxxxxx
HEDERA_PRIVATE_KEY=your_hedera_key
HEDERA_TOPIC_ID=0.0.xxxxxx

# APIs
PLANET_API_KEY=your_planet_key
AI_API_KEY=your_groq_key
AI_MODEL=deepseek-r1-distill-llama-70b
```

### Deploy Contract

```bash
# Using Python script (requires solcx)
pip install solc
python scripts/deploy_rsk.py

# Or using Foundry
forge create --rpc-url $RSK_RPC_URL --private-key $RSK_PRIVATE_KEY contracts/VitisRegistry.sol:VitisRegistry
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check (RSK & Hedera connections) |
| GET | `/verify-vineyard?lat=X&lon=Y&asset_address=Z&token_id=N` | Run full audit |
| GET | `/certificate/{asset_address}/{token_id}` | Query existing certificate |

---

## Architecture Notes

The system consists of four main components:

1. **Protocol Agent** (`agents/protocol_agent.py`): Notarizes audit results in
   Hedera Consensus Service (HCS)
2. **Perception Agent** (`agents/perception_agent.py`): Fetches satellite imagery
   (Sentinel-2 via Sentinel Hub) and calculates NDVI
3. **Reasoning Agent** (`agents/reasoning_agent.py`): Uses AI (DeepSeek-R1 via Groq)
   to analyze data and generate VitisScore
4. **Backend API** (`backend/main.py`): FastAPI app orchestrating the workflow and
   recording proofs on Hedera (HCS) and Rootstock (VitisRegistry.sol)
