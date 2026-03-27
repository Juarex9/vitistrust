# 🍇 VitisTrust Oracle

**Certificador descentralizado de viñedos tokenizados**

VitisTrust es un oráculo que audita la salud de viñedos usando datos satelitales e IA,
registrando las certificaciones en Hedera (HCS) y Rootstock (RSK) para garantizar
transparencia e inmutabilidad en inversiones agrícolas tokenizadas.

---

## 🎯 Qué Hace VitisTrust

VitisTrust resuelve el problema de la **falta de transparencia** en la tokenización
de activos agrícolas (RWA). Cuando un viñedo es tokenizado como NFT:

1. **El inversor necesita saber** si el viñedo está realmente sano
2. **El oráculo consulta** imágenes satelitales (NDVI)
3. **La IA analiza** los datos y genera un VitisScore (0-100)
4. **Hedera notariza** el resultado de forma inmutable
5. **Rootstock certifica** el NFT en un smart contract

El resultado: un historial auditable que nadie puede falsificar.

---

## 🏗️ Arquitectura

```
┌─────────────────────────────────────────────────────────────────┐
│                        VITISTRUST ORACLE                         │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐     │
│  │   USER       │───▶│   FASTAPI    │◀───│   VERIFY     │     │
│  │  (Frontend)  │    │   BACKEND    │    │  REQUEST    │     │
│  └──────────────┘    └──────┬───────┘    └──────────────┘     │
│                             │                                   │
│         ┌───────────────────┼───────────────────┐              │
│         ▼                   ▼                   ▼              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    │
│  │  PERCEPTION  │    │  REASONING   │    │  PROTOCOL    │    │
│  │   AGENT      │    │    AGENT     │    │    AGENT     │    │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘    │
│         │                   │                   │             │
│         ▼                   ▼                   ▼             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    │
│  │  SATELLITE   │    │   LLM (AI)   │    │   HEDERA     │    │
│  │  (Sentinel)  │    │   (Groq)     │    │   (HCS)      │    │
│  └──────────────┘    └──────────────┘    └──────────────┘    │
│         │                                       │              │
│         │                    ┌─────────────────┘              │
│         │                    ▼                                   │
│         │            ┌──────────────┐                            │
│         └───────────▶│  ROOTSTOCK   │◀── Smart Contract            │
│                      │    (RSK)     │    VitisRegistry            │
│                      └──────────────┘                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔄 Flujo de Auditoría

```
1.Usuario         Pide verificación con:
  Frontend         lat, lon, asset_address, token_id
      │
      ▼
2.Perception      Consulta Sentinel Hub para obtener
  Agent           datos NDVI de las coordenadas
      │
      ▼
3.Reasoning      Envía NDVI a Groq (Llama 3.3)
  Agent           Obtiene VitisScore, risk, justification
      │
      ▼
4.Protocol        Notariza el reporte en Hedera HCS
  Agent           Topic: 0.0.8386842
      │
      ▼
5.Backend         Firma transacción en Rootstock
  (main.py)       certifyAsset() en VitisRegistry
      │
      ▼
6.Usuario         Recibe certificación completa
```

---

## 📂 Estructura del Proyecto

```
vitistrust/
├── agents/                      # Agentes de IA
│   ├── perception_agent.py    # Satélite: Sentinel Hub → NDVI
│   ├── reasoning_agent.py      # IA: Groq → VitisScore + Investment Analysis
│   ├── protocol_agent.py       # Hedera: HCS → Notarización
│   └── validation_agent.py     # Validación: geolocalización, vegetation, ERC-721
├── backend/
│   ├── main.py                # FastAPI: Endpoints del oráculo
│   └── constants.py           # ABI del contrato VitisRegistry
├── frontend-react/             # React frontend
│   └── src/App.jsx            # Interfaz de usuario
├── contracts/
│   └── VitisRegistry.sol       # Smart Contract en RSK
├── scripts/
│   └── deploy_rsk.py          # Deploy del contrato
├── .env                       # Configuración (NOコミット)
├── requirements.txt            # Dependencias Python
└── README.md                   # Este archivo
```

---

## 🌐 APIs y Endpoints

### Endpoints del Oráculo

| Method | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/health` | Verifica conexiones a RSK y Hedera |
| GET | `/verify-vineyard?lat=X&lon=Y&asset_address=Z&token_id=N` | Ejecuta auditoría completa |
| GET | `/certificate/{asset_address}/{token_id}` | Consulta certificación existente |

### Ejemplo de Uso

```bash
# Auditar un viñedo
curl "http://localhost:8000/verify-vineyard?lat=-33.1254&lon=-68.8942&asset_address=0xTU_ADDRESS&token_id=1"

# Respuesta:
{
  "vitis_score": 75,
  "risk": "low",
  "justification": "El NDVI de 0.75 indica excelente salud vegetativa...",
  "hedera_notarization": "SUCCESS",
  "rsk_tx_hash": "0xabc123...",
  "status": "ASSET_CERTIFIED",
  "investment_analysis": {
    "recommendation": "BUY",
    "risk_score": 20,
    "yield_forecast": "10-12 tons/ha"
  }
}

# Consultar certificación previa
curl "http://localhost:8000/certificate/0xTU_ADDRESS/1"

# Verificar salud del oráculo
curl "http://localhost:8000/health"
```

---

## ⚙️ Configuración

### Variables de Entorno (.env)

```bash
# ===== ROOTSTOCK (RSK) =====
RSK_RPC_URL=https://public-node.testnet.rsk.co
RSK_PRIVATE_KEY=tu_private_key
RSK_ORACLE_ADDRESS=tu_direccion
RSK_CONTRACT_ADDRESS=0x1418344A54a065987B991574632CBd36114e308d

# ===== HEDERA / HIERO =====
HEDERA_ACCOUNT_ID=0.0.xxxxxx
HEDERA_DER_PRIVATE_KEY=3030020100300706052b8104000a04220420...
HEDERA_TOPIC_ID=0.0.xxxxxx

# ===== SATÉLITE =====
SENTINEL_CLIENT_ID=tu_client_id
SENTINEL_CLIENT_SECRET=tu_client_secret

# ===== IA (GROQ) =====
AI_API_KEY=tu_api_key
```

---

## 🚀 Instalación y Ejecución

### 1. Clonar e instalar dependencias

```bash
git clone https://github.com/tu-repo/vitistrust.git
cd vitistrust
python -m venv venv
venv\Scripts\activate  # Windows

pip install -r requirements.txt
```

### 2. Configurar .env

Copiar el ejemplo anterior y completar con tus claves.

### 3. Levantar el servidor

```bash
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Frontend

```bash
cd frontend-react
npm install
npm run dev
```

---

## 🧪 Tecnologías Utilizadas

| Capa | Tecnología | Propósito |
|------|------------|-----------|
| API | FastAPI + Uvicorn | Servidor REST |
| Satélite | Sentinel Hub (ESA) | Imágenes multiespectrales (NDVI) |
| IA | Groq (Llama 3.3) | Análisis de datos + Investment Analysis |
| Blockchain 1 | Hedera (HCS) | Notarización inmutable |
| Blockchain 2 | Rootstock (RSK) | Smart Contracts (EVM) |
| Frontend | React + Vite | Interfaz de usuario |

---

## 📋 Smart Contract

### VitisRegistry.sol (Rootstock)

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract VitisRegistry {
    struct Certificate {
        uint256 score;
        uint256 timestamp;
        string hederaTopic;
    }
    
    mapping(address => mapping(uint256 => Certificate)) public certificates;
    
    function certifyAsset(
        address assetContract,
        uint256 tokenId,
        uint256 score,
        string memory topicId
    ) public {
        certificates[assetContract][tokenId] = Certificate({
            score: score,
            timestamp: block.timestamp,
            hederaTopic: topicId
        });
    }
}
```

---

## 🔍 Explorando las Transacciones

### Hedera (HashScan)
- Topic: https://testnet.hashscan.io/topic/0.0.8386842

### Rootstock (RSK Explorer)
- Contrato: https://explorer.testnet.rsk.co/address/0x1418344A54a065987B991574632CBd36114e308d

---

## 💡 Nota para el Jurado

**VitisTrust resuelve un problema real:**

En la tokenización de viñedos, el inversor no puede verificar si el activo subyacente
realmente existe y está sano. VitisTrust resolve este problema:

1. **Satélite + IA**: Datos objetivos, no manipulables
2. **Doble blockchain**: Hedera para consenso + Rootstock para seguridad Bitcoin
3. **Inmutable**: Cada auditoría queda registrada para siempre
4. **Descentralizado**: Nadie puede falsificar un certificado
5. **Análisis de Inversión**: BUY/HOLD/SELL para inversores

> "VitisTrust trae transparencia verificable al mercado de vinos tokenizados."

---

## 🏆 Estado del Proyecto

| Componente | Estado |
|------------|--------|
| Smart Contract | ✅ Desplegado en RSK Testnet |
| Backend API | ✅ Funcionando |
| Frontend | ✅ React sin wallet |
| Hedera HCS | ✅ Notarización activa |
| Análisis IA | ✅ Investment Analysis |

---

## 📄 Licencia

MIT License - Ver archivo LICENSE para detalles.
