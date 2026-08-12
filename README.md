# 🍇 VitisTrust Oracle

**Certificador descentralizado de viñedos tokenizados**

VitisTrust es un oráculo que audita la salud de viñedos usando datos satelitales e IA,
registrando las certificaciones en Hedera (HCS - Trust Layer) y Rootstock (EVM / VitisRegistry — Asset Layer)
para garantizar transparencia e inmutabilidad en inversiones agrícolas tokenizadas.

---

## 🎯 Qué Hace VitisTrust

VitisTrust resuelve el problema de la **falta de transparencia** en la tokenización
de activos agrícolas (RWA). Cuando un viñedo es tokenizado como NFT:

1. **El inversor necesita saber** si el viñedo está realmente sano
2. **El oráculo consulta** imágenes satelitales (NDVI)
3. **La IA analiza** los datos y genera un VitisScore (0-100) e informe detallado
4. **Hedera notariza** el resultado de forma inmutable (Trust Layer)
5. **Rootstock (RSK)** registra la certificación on-chain con `VitisRegistry.sol` (Asset Layer)

El resultado: un historial auditable que nadie puede falsificar.

---

## 🏗️ Arquitectura

```
┌─────────────────────────────────────────────────────────────────┐
│                    VITISTRUST ORACLE                    │
├──────────────────────────────���──────────────────────────────────┤
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
│         │                                            │              │
│         │                    ┌─────────────────┘              │
│         │                    ▼                                   │
│         │            ┌──────────────┐                        │
│         └───────────▶│  ROOTSTOCK   │◀── VitisRegistry.sol       │
│                      │  (RSK EVM)   │                           │
│                      └──────────────┘                        │
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
5.Backend         Envía `certifyAsset` a VitisRegistry en Rootstock
   (main.py)       Actualiza estado del contrato
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
│   └── validation_agent.py     # Validación: geolocalización, vegetation
├── backend/
│   ├── main.py                # FastAPI: Endpoints del oráculo
│   ├── rootstock_adapter.py   # Rootstock / Web3 — VitisRegistry
│   └── constants.py           # ABI del contrato
├── frontend-react/             # React frontend
│   └── src/App.jsx            # Interfaz de usuario
├── contracts/
│   └── VitisRegistry.sol       # Contrato Solidity (EVM)
├── scripts/
│   └── deploy_rsk.py          # Deploy a RSK testnet/mainnet
├── .env                       # Configuración (NO commit)
├── requirements.txt            # Dependencias Python
└── README.md                   # Este archivo
```

---

## 🌐 APIs y Endpoints

### Endpoints del Oráculo

| Method | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/health` | Hedera + Rootstock (métricas / stub) |
| GET | `/certificate/{farm_id}` | Lectura on-chain (`asset_address`, `token_id` query) |
| POST | `/verify-vineyard` | Ejecuta auditoría completa |
| GET | `/verify-vineyard` | Ejecuta auditoría (GET) |

### Ejemplo de Uso

```bash
# Auditar un viñedo
curl "http://localhost:8000/verify-vineyard?lat=-33.1254&lon=-68.8942&farm_id=mendoza_1"

# Respuesta:
{
  "vitis_score": 75,
  "risk": "low",
  "justification": "El NDVI de 0.75 indica excelente salud vegetativa...",
  "ndvi": 0.7512,
  "satellite_img": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...",
  "hedera_notarization": "SUCCESS",
  "rootstock_tx_hash": "0x3f08e6f94f7f0f4f3fa7491d58dd4d0f1d6b9ca2d31e2e8c4e...",
  "hedera_txn_id": "0.0.1234567@1713659342.000001",
  "status": "ASSET_CERTIFIED",
  "investment_analysis": {
    "recommendation": "BUY",
    "risk_score": 20,
    "yield_forecast": "10-12 tons/ha"
  },
  "validation": {
    "all_valid": true,
    "can_verify": true,
    "validations": {
      "geolocation": {
        "valid": true,
        "region": "Valle de Uco",
        "region_key": "VALLE_DE_UCO",
        "message": "Coordinates within Valle de Uco"
      },
      "vegetation": {
        "valid": true,
        "health": "high",
        "message": "Vegetation detected (NDVI: 0.7512, health: high)"
      },
      "contract": null,
      "token": null,
      "certificate": null
    }
  },
  "lat": -33.1254,
  "lon": -68.8942,
  "source": "sentinel_hub"
}

# Consultar certificación previa
curl "http://localhost:8000/certificate/mendoza_1"

# Verificar salud del oráculo
curl "http://localhost:8000/health"
```

### Schema final de `/verify-vineyard`

```json
{
  "vitis_score": "int",
  "risk": "str",
  "justification": "str",
  "ndvi": "float",
  "satellite_img": "str (base64 data URL)",
  "hedera_notarization": "str",
  "rootstock_tx_hash": "str",
  "hedera_txn_id": "str",
  "status": "str",
  "investment_analysis": "dict[str, Any] | null",
  "validation": {
    "all_valid": "bool",
    "can_verify": "bool",
    "validations": {
      "geolocation": "dict[str, Any]",
      "vegetation": "dict[str, Any]",
      "contract": "dict[str, Any] | null",
      "token": "dict[str, Any] | null",
      "certificate": "dict[str, Any] | null"
    }
  },
  "lat": "float | null",
  "lon": "float | null",
  "source": "str | null"
}
```

---

## ⚙️ Configuración

### Variables de Entorno (.env)

```bash
# ===== HEDERA (Trust Layer) =====
HEDERA_ACCOUNT_ID=0.0.xxxxxx
HEDERA_DER_PRIVATE_KEY=3030020100300706052b8104000a04220420...
HEDERA_TOPIC_ID=0.0.xxxxxx

# ===== ROOTSTOCK / RSK (Asset Layer) =====
RSK_RPC_URL=https://public-node.testnet.rsk.co
RSK_CONTRACT_ADDRESS=0x...
RSK_PRIVATE_KEY=0x...
# RSK_CHAIN_ID=31
RSK_NETWORK=rsk-testnet

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
git clone https://github.com/Juarex9/vitistrust.git
cd vitistrust
# Recomendado: Python 3.13 para compatibilidad con Hedera SDK
py -3.13 -m venv venv
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
| IA | Groq (Llama 3.3 70B) | Análisis de datos + Investment Analysis |
| Blockchain 1 | Hedera (HCS) | Notarización inmutable (Trust Layer) |
| Blockchain 2 | Rootstock (RSK, EVM) | VitisRegistry.sol (Asset Layer) |
| Frontend | React + Vite | Interfaz de usuario |

---

## 📋 Smart Contract

El registro on-chain está en `contracts/VitisRegistry.sol` (Solidity). El oráculo llama a `certifyAsset(assetContract, tokenId, score, topicId)`; `topicId` enlaza con la notarización en Hedera (p. ej. ID de transacción HCS o el topic).

Despliegue de ejemplo: `python scripts/deploy_rsk.py` (requiere `RSK_RPC_URL` y `RSK_PRIVATE_KEY`).

## 🔍 Explorando las Transacciones

### Hedera (HashScan)
- Topic: https://testnet.hashscan.io/topic/0.0.8386842

### Rootstock (RSK explorer)
- Por red: busca el `RSK_CONTRACT_ADDRESS` en el explorador de la red que uses (testnet/mainnet).

## 💡 Nota para el Jurado

**VitisTrust resuelve un problema real:**

En la tokenización de viñedos, el inversor no puede verificar si el activo subyacente
realmente existe y está sano. VitisTrust resolve este problema:

1. **Satélite + IA**: Datos objetivos, no manipulables
2. **Doble blockchain**: Hedera HCS para auditoría + Rootstock (EVM) para la certificación en `VitisRegistry`
3. **Inmutable**: Cada auditoría queda registrada para siempre
4. **Descentralizado**: Nadie puede falsificar un certificado
5. **Análisis de Inversión**: BUY/HOLD/SELL para inversores
6. **EVM en Bitcoin**: Rootstock aprovecha la seguridad de Bitcoin con compatibilidad Ethereum

> "VitisTrust trae transparencia verificable al mercado de vinos tokenizados."

---

## 🏆 Estado del Proyecto

| Componente | Estado |
|------------|--------|
| Smart Contract | ⚠️ Código listo (compilar + deploy) |
| Backend API | ✅ Funcionando |
| Frontend | ✅ React (actualizado) |
| Hedera HCS | ✅ Notarización activa |
| Rootstock adapter | ✅ `backend/rootstock_adapter.py` |

---

## 📄 Licencia

MIT License - Ver archivo LICENSE para detalles.
