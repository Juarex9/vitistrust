# Stellar Cowork - Presentación VitisTrust

## 🗓️ Fecha
Jueves - Preparate 10-15 minutos de presentación

---

## 🎯 Tu Propuesta de Valor (30 segundos)

> **"Soy el único en Stellar que verifica activos agrícolas reales usando datos satelitales + IA. No soy un price feed genérico — verifico que un viñedo existe y está sano."**

Esto te diferencia porque:
- Los oráculos de Stellar son 99% price feeds (XLM/USDC, etc)
- Vos verificás el mundo físico (agricultura)
- Es un caso de uso REAL, no demo

---

## 🏗️ Arquitectura (3-4 minutos)

```
┌─────────────────────────────────────────────────────────────────┐
│                    VITISTRUST ORACLE                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. SATELLITE (Sentinel-2)                                     │
│     - Imágenes multiespectrales                                │
│     - NDVI: (NIR-Red)/(NIR+Red)                               │
│     - Resolución 10m                                           │
│           │                                                     │
│           ▼                                                     │
│  2. AI (DeepSeek-R1 via Groq)                                  │
│     - Análisis agronómico                                      │
│     - VitisScore (0-100)                                       │
│     - Riesgo: LOW/MEDIUM/HIGH                                 │
│           │                                                     │
│           ▼                                                     │
│  3. HEDERA HCS (Trust Layer)                                  │
│     - Notarización inmutable                                    │
│     - Audit trail                                             │
│     - Topics: 0.0.8386842                                      │
│           │                                                     │
│           ▼                                                     │
│  4. STELLAR SOROBAN (Asset Layer) ⭐                          │
│     - Smart contract: VitisRegistry                           │
│     - Storage: Map<farm_id, VitisRecord>                     │
│     - Auth: Only oracle can update                            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 💻 Código Soroban (2-3 minutos)

### Storage: Map<Symbol, VitisRecord>

```rust
// structs.rs
struct VitisRecord {
    score: u32,              // 0-100
    timestamp: u64,         // Unix
    hedera_txn_id: BytesN<32>,
    auditor: Address,
}
```

### Función de update (solo admin):

```rust
pub fn update_score(
    env: Env,
    farm_id: Symbol,       // "mendoza_1"
    score: u32,            // 85
    hedera_txn_id: BytesN<32>,
) {
    // Solo el oráculo puede actualizar
    let admin = get_admin();
    admin.require_auth();
    
    // Guardar registro
    records.set(farm_id, VitisRecord { ... });
}
```

**Por qué Stellar?**
- Costo: $0.0001 por tx (vs $1+ en EVM)
- Velocidad: 3-5 segundos finality
- Integración con tokens SPL (para futuros NFTs de viñedos)

---

## 💰 Modelo de Negocio

### Target:
1. **Viñedos que quieren tokenizar** (Acceso a capital global)
2. **Inversores en RWA** (Confianza para invertir)
3. **Plataformas de tokenización** (Como servicio de verificación)

### Revenue Stream:
- **Por auditoría**: $5-15 por verificación
- **Suscripción**: $100-500/mes para vineyards (monitoreo continuo)
- **API Enterprise**: $2000+/mes para plataformas

### Unit Economics:
- Costo por verificación: ~$0.10 (Sentinel API)
- Precio: $5-15
- Margen: 98% 🤑

### Market Size:
- Wine market global: $340B+
- Vineyard tokenization: Emerging ($12B projected 2025)
- Tu TAM: Verificadores de RWA agrícolas

---

## 🎤 Guión de Presentación

### Intro (30 seg):
"Todos los oráculos de blockchain son price feeds. Yo verifico que los viñedos del mundo real existen y están sanos."

### Problema (1 min):
- Inversores no pueden verificar viñedos tokenizados
- No hay forma de saber si el activo subyacente existe
- Se pierden miles de millones en inversiones

### Solución (2 min):
"VitisTrust usa Sentinel-2 + AI para auditar viñedos. Cada auditoría queda registrada en Hedera + Stellar."

### Demo (2 min):
- Mostrar el frontend
- Explicar el flujo

### Tech (2 min):
- Código del contrato Soroban
- Explicar la autorización

### Cierre (30 seg):
"Busco: feedback técnico, potenciales usuarios piloto, y conectarme con el ecosistema Stellar."

---

## ❓ Preguntas Que Van a Hacer

### "Por qué no Rootstock?"
- Ya no está activo en mi roadmap
- Stellar tiene mejor integración con tokens
- Costos más bajos

### "Por qué no usás Chainlink?"
- Chainlink no tiene datos agrícolas
- Es para price feeds, no verificación de activos físicos
- Somos complementarios, no competidores

### "Cómo asegurás que el oráculo no miente?"
- Datos satelitales son objetivos (no los elijo yo)
- Hedera es el audit trail
- Código abierto

### "Qué pasa si Sentinel se cae?"
- Tengo fallback con datos históricos
- Para producción: múltiples fuentes de datos satelitales

---

## ✅ Checklist Antes del Cowork

- [ ] Instalar Rust + cargo
- [ ] Compilar contrato: `cargo build --release`
- [ ] Deploy a testnet: `stellar contract deploy`
- [ ] Probar endpoint `/health`
- [ ] Probar endpoint `/verify-vineyard` con fallback
- [ ] Preparar laptop con demo funcionando

---

## 🔧 Commands Para Probar

```bash
# Instalar Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Compilar contrato
cd contracts/vitis_registry
cargo build --release

# Deploy a testnet
stellar contract deploy \
  --wasm target/wasm32-unknown-unknown/release/vitis_registry.wasm \
  --source testnet \
  --network testnet

# Guardar contract ID en .env
echo "SOROBAN_CONTRACT_ID=CA..." >> .env
```

---

## 📚 Recursos

- [Soroban Docs](https://developers.stellar.org/docs/smart-contracts)
- [stellar-sdk Python](https://stellar-sdk.readthedocs.io/)
- [Freighter Wallet](https://www.freighter.app/)
- [Sentinel Hub](https://www.sentinel-hub.com/)
