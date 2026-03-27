# SLIDE 1: EL PROBLEMA

---

## El Problema

### 💰 Activos tokenizados de viñedos = +$12B en 2025

Pero...

---

### ❌ El inversor no puede verificar:

**1. ¿Existe realmente el viñedo?**
> Cualquer NFT puede decir "viñedo en Mendoza", pero nadie lo verifica

**2. ¿Está saludable?**
> El viñedo podría estar seco, enfermo o abandonado

**3. ¿El rendimiento es real?**
> Sin datos objetivos, es solo marketing

---

### 😰 El resultado:

```
┌─────────────────────────────────────────────┐
│                                             │
│   Fondos de inversión RECHAZAN activos RWA   │
│                                             │
│   • Falta de confianza                      │
│   • Sin verificación objetiva               │
│   • Riesgo de fraude                       │
│                                             │
└─────────────────────────────────────────────┘
```

---

### 💡 Necesidad urgente:

> **Un sistema de verificación objetiva, independiente y on-chain que certifique la salud real de los viñedos tokenizados**

---

---

# SLIDE 2: LA SOLUCIÓN

---

## VitisTrust: Oracle de Confianza para Viñedos Tokenizados

---

### 🔮 Qué hacemos:

**VitisTrust es un oracle que certifica la salud de viñedos usando:**
- 📡 Imágenes satelitales (NDVI)
- 🤖 Inteligencia artificial agronómica
- ⛓️ Pruebas en blockchain inmutable

---

### 🚀 Cómo funciona:

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│   INVERSOR                                                        │
│      │                                                           │
│      ▼                                                            │
│   ┌─────────┐     ┌─────────────┐     ┌──────────┐              │
│   │Dashboard│────▶│Satellite API│────▶│   AI     │              │
│   └─────────┘     │  Sentinel-2 │     │DeepSeek  │              │
│                   └─────────────┘     └────┬─────┘              │
│                                            │                     │
│                                            ▼                     │
│                   ┌──────────────┐   ┌──────────────┐          │
│                   │  Hedera HCS  │◀──│  VitisScore  │          │
│                   │  (Notarized) │   │  0-100       │          │
│                   └──────────────┘   └──────┬───────┘          │
│                                            │                     │
│                                            ▼                     │
│                                    ┌──────────────┐             │
│                                    │  Rootstock   │             │
│                                    │  VitisRegistry│             │
│                                    └──────┬───────┘             │
│                                           │                     │
│                                           ▼                     │
│                                    ✅ CERTIFICADO                │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

### 📊 Qué recibe el inversor:

```
┌────────────────────────────────────────────────┐
│                                                │
│   🍇 VITISSCORE: 85/100                        │
│                                                │
│   📍 Ubicación verificada                      │
│   🌿 Salud: EXCELENTE                         │
│   💰 Recomendación: BUY                        │
│                                                │
│   ─────────────────────────────────────────    │
│                                                │
│   🔗 Hedera Topic: 0.0.12345 (audit trail)   │
│   ⬡ RSK TX: 0x7f8e... (on-chain proof)      │
│                                                │
└────────────────────────────────────────────────┘
```

---

### 🎯 Diferenciadores:

| Tradiocional | VitisTrust |
|--------------|------------|
| Documentación PDF | Datos satelitales reales |
| Auditorías manuales | Verificación automatizada |
| Confianza subjetiva | Pruebas blockchain |
| Actualización anual | Near real-time |
| Sin追溯性 | Historial inmutable |

---

### 💡 Propuesta de valor:

> **VitisTrust transforma "palabras" en "datos verificables"**
> 
> Para inversores → Confianza para invertir
> 
> Para viñedos → Acceso a capital global
> 
> Para el ecosistema → Liquidez en activos RWA

---

---

# SLIDE 3: TECH STACK

---

## Stack Tecnológico

### Un oracle completo con tecnologías de vanguardia

---

### 🛰️ Percepción (Satélite)

```
┌─────────────────────────────────────────┐
│                                         │
│   SENTINEL-2 (ESA)                      │
│                                         │
│   • Resolución: 10m                      │
│   • Revisita: 5 días                     │
│   • Bandas: NIR + Red (NDVI)           │
│                                         │
│   NDVI = (NIR - Red) / (NIR + Red)     │
│                                         │
│   0.0 = Suelo desnudo                   │
│   0.5 = Vegetación moderada             │
│   0.8+ = Vegetación saludable           │
│                                         │
└─────────────────────────────────────────┘
```

---

### 🧠 Razonamiento (AI)

```
┌─────────────────────────────────────────┐
│                                         │
│   GROQ + DEEPSEEK-R1                    │
│                                         │
│   • Análisis agronómico experto         │
│   • Factores de riesgo                  │
│   • Recomendación de inversión          │
│   • Yield forecast                      │
│                                         │
│   Ejemplo de output:                    │
│   {                                     │
│     "score": 85,                       │
│     "risk_level": "low",               │
│     "recommendation": "BUY",           │
│     "yield_forecast": "10-12 tons/ha" │
│   }                                     │
│                                         │
└─────────────────────────────────────────┘
```

---

### ⛓️ Protocolo (Blockchain)

```
┌────────────────────────┬────────────────────────────────┐
│                        │                                │
│   HEDERA               │   ROOTSTOCK                    │
│   (Consensus Service)  │   (EVM Smart Contract)        │
│                        │                                │
│   • Notarización       │   • VitisRegistry.sol         │
│   • Audit trail        │   • VitisScore on-chain       │
│   • Immutable log      │   • Token certification       │
│   • Mirror node query  │   • Batch certification       │
│                        │                                │
│   ⭐ 10k TPS           │   ⭐ EVM compatible            │
│   ⭐ <3s finality      │   ⭐ Bitcoin security          │
│   ⭐ $0.001 TX         │   ⭐ RBTC gas                 │
│                        │                                │
└────────────────────────┴────────────────────────────────┘
```

---

### 🔗 Flujo Completo de Datos

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│   COORDENADAS           NDVI              AI ANALYSIS              │
│   (-33.4, -69.2)  ───▶  0.75  ─────────▶  Score: 75               │
│                                                                     │
│         │                                        │                 │
│         │                                        ▼                 │
│         │                              ┌─────────────────┐         │
│         │                              │  Hedera HCS     │         │
│         │                              │  Notarization   │         │
│         │                              │  TX: 0.0.12345  │         │
│         │                              └────────┬────────┘         │
│         │                                       │                   │
│         │                                       ▼                   │
│         │                              ┌─────────────────┐         │
│         │                              │  Rootstock      │         │
│         │                              │  certifyAsset() │         │
│         │                              │  TX: 0x7f8e...  │         │
│         │                              └─────────────────┘         │
│         │                                       │                   │
│         └───────────────────────────────────────┘                   │
│                                                                     │
│   ✅ TODAS LAS PRUEBAS ON-CHAIN                                    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

### 🏗️ Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   FRONTEND (React)                                          │
│   Dashboard + Visualización + API calls                     │
│                                                             │
│         │                                                   │
│         ▼                                                   │
│   ┌─────────────────┐                                       │
│   │   BACKEND       │                                       │
│   │   FastAPI       │                                       │
│   │                 │                                       │
│   │  ┌───────────┐  │                                       │
│   │  │ Perception│  │  ┌───────────┐  ┌───────────────┐   │
│   │  │ Agent     │──│──│ Reason    │──│  Protocol     │   │
│   │  │ (NDVI)    │  │  │ Agent(AI) │  │  Agent(HCS)   │   │
│   │  └───────────┘  │  └───────────┘  └───────┬───────┘   │
│   │                 │                         │             │
│   └─────────────────┴─────────────────────────┘             │
│                            │                                 │
│                            ▼                                 │
│                   ┌─────────────────┐                        │
│                   │  ROOTSTOCK      │                        │
│                   │  VitisRegistry │                        │
│                   │  Smart Contract │                        │
│                   └─────────────────┘                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

### 🛠️ Stack Completo

| Capa | Tecnología |
|------|------------|
| **Frontend** | React + Vite + CSS |
| **Backend** | FastAPI + Python |
| **Satellite** | Sentinel-2 via Sentinel Hub |
| **AI** | Groq + DeepSeek-R1 |
| **Consensus** | Hedera HCS |
| **Smart Contract** | Solidity + Rootstock EVM |
| **DevOps** | Foundry (contracts) |

---

### 🔐 Seguridad

- ✅ Smart contracts auditados
- ✅ Multi-source verification
- ✅ Immutable audit trail
- ✅ Oracle permissions controladas
- ✅ Testnet validado

---

## Resumen

> **VitisTrust = Satellite + AI + Blockchain**
> 
> Un stack poderoso para certificar activos reales en el mundo digital

---

