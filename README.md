# 🍇 VitisTrust Oracle

**Certificador descentralizado de viñedos tokenizados**

VitisTrust es un oráculo que audita la salud de viñedos usando datos satelitales e IA,
registrando las certificaciones en Hedera (HCS - Trust Layer) y Stellar Soroban (Asset Layer)
para garantizar transparencia e inmutabilidad en inversiones agrícolas tokenizadas.

---

## 🎯 Qué Hace VitisTrust

VitisTrust resuelve el problema de la **falta de transparencia** en la tokenización
de activos agrícolas (RWA). Cuando un viñedo es tokenizado como NFT:

1. **El inversor necesita saber** si el viñedo está realmente sano
2. **El oráculo consulta** imágenes satelitales (NDVI)
3. **La IA analiza** los datos y genera un VitisScore (0-100) e informe detallado
4. **Hedera notariza** el resultado de forma inmutable (Trust Layer)
5. **Stellar Soroban** almacena el VitisScore on-chain (Asset Layer)

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
│         └───────────▶│  STELLAR     │◀── Soroban Contract      │
│                      │  SOROBAN     │    VitisRegistry          │
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
│   └── validation_agent.py     # Validación: geolocalización, vegetation
├── backend/
│   ├── main.py                # FastAPI: Endpoints del oráculo
│   ├── stellar_adapter.py     # Stellar Soroban adapter
│   └── constants.py           # ABI del contrato
├── frontend-react/             # React frontend
│   └── src/App.jsx            # Interfaz de usuario
├── contracts/
│   └── vitis_registry/         # Smart Contract en Soroban (Rust)
├── scripts/
│   └── deploy_soroban.py      # Deploy del contrato Soroban
├── .env                       # Configuración (NO commit)
├── requirements.txt            # Dependencias Python
└── README.md                   # Este archivo
```

---

## 🌐 APIs y Endpoints

### Endpoints del Oráculo

| Method | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/health` | Verifica conexiones a Hedera y Stellar |
| POST | `/verify-vineyard` | Ejecuta auditoría completa |
| GET | `/verify-vineyard` | Ejecuta auditoría (GET) |
| GET | `/certificate/{farm_id}` | Consulta certificación existente |

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
  "stellar_tx_hash": "3f08e6f94f7f0f4f3fa7491d58dd4d0f1d6b9ca2d31e2e8c4e...",
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
  "stellar_tx_hash": "str",
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

# ===== STELLAR SOROBAN (Asset Layer) =====
STELLAR_NETWORK=testnet
STELLAR_RPC_URL=https://soroban-testnet.stellar.org:443
STELLAR_ORACLE_SECRET=tu_stellar_secret
SOROBAN_CONTRACT_ID=CA...

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
| IA | Groq (DeepSeek-R1) | Análisis de datos + Investment Analysis |
| Blockchain 1 | Hedera (HCS) | Notarización inmutable (Trust Layer) |
| Blockchain 2 | Stellar Soroban | Smart Contracts (Asset Layer) |
| Frontend | React + Vite | Interfaz de usuario |

---

## 📋 Smart Contract

### VitisRegistry (Soroban/Rust)

```rust
// contracts/vitis_registry/src/lib.rs
// Almacena VitisScores en Stellar Soroban

struct VitisRecord {
    score: u32,              // 0-100
    timestamp: u64,         // Unix
    hedera_txn_id: BytesN<32>,
    auditor: Address,
}

pub fn update_score(
    env: Env,
    farm_id: Symbol,       // "mendoza_1"
    score: u32,            // 85
    hedera_txn_id: BytesN<32>,
) {
    // Solo el oráculo puede actualizar
    admin.require_auth();
    records.set(farm_id, record);
}
```

---

## 🔍 Explorando las Transacciones

### Hedera (HashScan)
- Topic: https://testnet.hashscan.io/topic/0.0.8386842

### Stellar (StellarBeat)
- Contract: https://stellarbeat.io/contract/{SOROBAN_CONTRACT_ID}

---

## 💡 Nota para el Jurado

**VitisTrust resuelve un problema real:**

En la tokenización de viñedos, el inversor no puede verificar si el activo subyacente
realmente existe y está sano. VitisTrust resolve este problema:

1. **Satélite + IA**: Datos objetivos, no manipulables
2. **Doble blockchain**: Hedera HCS para consenso + Stellar Soroban para storage on-chain
3. **Inmutable**: Cada auditoría queda registrada para siempre
4. **Descentralizado**: Nadie puede falsificar un certificado
5. **Análisis de Inversión**: BUY/HOLD/SELL para inversores
6. **Costos ultra-bajos**: Stellar Soroban vs EVM

> "VitisTrust trae transparencia verificable al mercado de vinos tokenizados."

---

## 🏆 Estado del Proyecto

| Componente | Estado |
|------------|--------|
| Smart Contract | ⚠️ Código listo (compilar + deploy) |
| Backend API | ✅ Funcionando |
| Frontend | ✅ React (actualizado) |
| Hedera HCS | ✅ Notarización activa |
| Stellar Adapter | ✅ Código listo |

---

## 📄 Licencia

MIT License - Ver archivo LICENSE para detalles.
