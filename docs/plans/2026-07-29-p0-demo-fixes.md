# Plan P0 — VitisTrust: Demo Lista para Startup World Cup

> **Para Hermes:** ejecutar task por task cuando el usuario dé la señal. Strict TDD activo: cada fix de código lleva su test de regresión.

**Goal:** Eliminar los 5 hallazgos P0 que rompen o exponen la demo en vivo frente a inversores (evento: 21 agosto 2026, Aleph Hub, CABA).

**Architecture:** Frontend React 19 + Vite (Vercel) → proxy /api → Backend FastAPI (Render) → pipeline Sentinel-2 → Groq → Hedera HCS → Stellar Soroban (testnet).

**Tech Stack:** React/Vite, FastAPI/Python, Rust/soroban-sdk 20, stellar-cli.

---

## Decisiones registradas (29 jul 2026)

- "Testnet" en footer SE QUEDA — la arquitectura real es Hedera + Stellar y se muestra honesto.
- Ejecución: SOLO cuando el usuario confirme.
- Debate RSK (matar vs dejar como multi-chain): PENDIENTE — no toca este plan salvo el link roto del modal (que es un bug factual, no una decisión de stack).

---

## Inventario completo de hallazgos

### P0 — rompen/exponen la demo

1. **OracleModal roto en producción** — `frontend-react/src/components/OracleModal.jsx:29-39` usa `t.oracle.*` (no existe en `App.jsx` translations → muestra "undefined"), lee `result.rsk_tx_hash` (la API devuelve `stellar_tx_hash`) y linkea a `explorer.testnet.rsk.co` (chain abandonada). El ítem Hedera (líneas 15-27, hashscan) está correcto.
2. **KeyError si Groq falla** — `agents/reasoning_agent.py:209`: `_fallback_verdict` referencia `SCORE_WEIGHTS["ai_reliability"]` y esa key no existe (líneas 16-22). Además omite `regional_benchmark`. Bonus: `ai_reliability` se calcula en línea 67 y nunca se usa (variable muerta). Resultado: HTTP 500 en vivo justo cuando el LLM está caído.
3. **CORS inválido** — `backend/main.py:51-57`: `allow_origins=["*"]` + `allow_credentials=True` viola la spec; browsers lo rechazan.
4. **URL backend inconsistente + deploy sin verificar** — `frontend-react/vercel.json:8` proxea a `vitistrust.onrender.com`, `VerifySection.jsx:6` fallback idem, pero `DEPLOY.md:86` dice `vitistrust-api.onrender.com`. No hay `render.yaml`; no hay evidencia de que el backend esté deployado.
5. **Soroban es teatro hoy** — contrato no compila con rustc 1.75 (soroban-sdk 20 pide edition2024); queries `get_vitis_score`/`has_record` → `NotImplementedError`; `stellar_adapter.py:~201` retorna tx hash falso sin esperar confirmación; no existe `scripts/deploy_stellar.py` (referenciado en `agents.md`); no hay `SOROBAN_CONTRACT_ID` real.

### P1 — percepción de inversor (post-P0)

- Letra "s" suelta visible en `HomeSection.jsx:56`
- "v2.0" hardcoded en `Navbar.jsx:13`
- Email ficticio `hola@vitistrust.io` en `AboutSection.jsx:52`
- Mezcla de idiomas en stats (`HomeSection.jsx:51-54`) y `HowItWorksSection.jsx:8` fijo en inglés
- Sin logo real (favicon genérico) — también requerido por el form de aplicación (branding kit)
- Historial NDVI sintético con seed determinista `lat*lon` (`backend/main.py:753-771`)
- Dual stack Stellar + RSK sin fuente de verdad documentada
- ABI Solidity desactualizada en `backend/constants.py:34`

### P2 — deuda sana (post-pitch)

- Tests del stellar adapter rotos (`tests/test_stellar_adapter.py` llama métodos inexistentes)
- Map monolítico en instance storage Soroban (`contracts/vitis_registry/src/lib.rs:91-97`) — no escala
- `panic!` en queries (`lib.rs:113-115`, `226-228`) en vez de Result
- `requirements.txt` raíz y `backend/requirements.txt` inconsistentes; `pyproject.toml` vacío
- Código legacy web3/ERC-721 muerto en `agents/validation_agent.py:221-379`
- 6 vulns high en deps npm (`npm audit fix`); `minify: false` en `vite.config.js:8-9`
- Componentes sin usar: `VerificationForm.jsx`, `SatelliteView.jsx`, `TimeMachine.jsx`
- Sin eventos en `initialize`/`set_location` del contrato; tests faltantes para `set_location`/`get_history`

---

## Plan de ejecución P0

### Task 1: Fix CORS (backend)

**Files:** Modify `backend/main.py:51-57`

**Step 1 — implementación:**

```python
ALLOWED_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "https://vitistrust.vercel.app,http://localhost:5173,http://localhost:4173",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Nota: confirmar la URL real de Vercel al ejecutar (puede ser otro subdominio) y agregarla a `CORS_ORIGINS` en Render.

**Step 2 — verificación:** `cd /root/vitistrust && python -c "from backend.main import app"` (importa sin error) + revisar que un request con `Origin: https://vitistrust.vercel.app` recibe header `access-control-allow-origin` correcto.

**Step 3 — commit:** `fix(backend): replace wildcard CORS with explicit origin allowlist`

### Task 2: Fix KeyError en _fallback_verdict (TDD)

**Files:** Modify `agents/reasoning_agent.py:204-210`; Test: `tests/test_reasoning_agent.py` (crear si no existe)

**Step 1 — test que falla:**

```python
from agents.reasoning_agent import _fallback_verdict, SCORE_WEIGHTS

def test_fallback_verdict_no_crashes_and_matches_weights():
    result = _fallback_verdict("test error")
    components = result["score_breakdown"]["components"]
    assert set(components.keys()) == set(SCORE_WEIGHTS.keys())
    assert result["score"] == 0
```

**Step 2 — correr y verificar falla:** `pytest tests/test_reasoning_agent.py::test_fallback_verdict_no_crashes_and_matches_weights -v` → KeyError: 'ai_reliability'

**Step 3 — fix (generar components desde el dict — no puede volver a desincronizarse):**

```python
        "components": {
            key: {"weight": weight, "component_score": 0.0, "contribution": 0.0}
            for key, weight in SCORE_WEIGHTS.items()
        },
```

**Step 4 — test pasa.** **Step 5 — commit:** `fix(agents): build fallback score components from SCORE_WEIGHTS (KeyError crash)`

### Task 3: Fix OracleModal — traducciones faltantes

**Files:** Modify `frontend-react/src/App.jsx` (locale `en` ~línea 23, locale `es` ~línea 36)

**Step 1 — agregar a `en`:**

```js
    oracle: { title: 'On-Chain Proof', subtitle: 'Immutable audit record', hederaTopic: 'Hedera HCS Topic', stellarTx: 'Stellar Soroban TX', viewExplorer: 'View in explorer', close: 'Close' },
```

**Step 2 — agregar a `es`:**

```js
    oracle: { title: 'Prueba On-Chain', subtitle: 'Registro inmutable de auditoría', hederaTopic: 'Topic de Hedera HCS', stellarTx: 'TX Stellar Soroban', viewExplorer: 'Ver en explorer', close: 'Cerrar' },
```

**Step 3 — verificación:** `cd frontend-react && npm run build` → compila; levantar dev server y abrir el modal con un resultado mock: no hay "undefined".

**Step 4 — commit:** `fix(frontend): add missing oracle modal translations (undefined texts)`

### Task 4: Fix OracleModal — campo y explorer de Stellar

**Files:** Modify `frontend-react/src/components/OracleModal.jsx:29-39`

**Step 1 — cambios:**

```jsx
          <div className="modal-item">
            <div className="modal-label">⬡ {t.oracle.stellarTx}</div>
            <div className="modal-value">
              {result.stellar_tx_hash}
              <a
                href={`https://stellar.expert/explorer/testnet/tx/${result.stellar_tx_hash}`}
                target="_blank"
                className="modal-link"
              >
                {t.oracle.viewExplorer} ↗
              </a>
            </div>
          </div>
```

Pre-requisito: confirmar que la API devuelve `stellar_tx_hash` en la respuesta de auditoría (grep en `backend/main.py` al ejecutar). Si el campo tiene otro nombre, usar el real.

**Step 2 — verificación:** build OK + click en "Ver en explorer" abre stellar.expert testnet.

**Step 3 — commit:** `fix(frontend): point oracle modal to stellar explorer and stellar_tx_hash field`

### Task 5: Unificar URL del backend y verificar deploy

**Files:** Modify `frontend-react/vercel.json:8`, `frontend-react/src/sections/VerifySection.jsx:6`, `DEPLOY.md`

**Step 1 — descubrir la verdad:** `curl -sS -m 20 https://vitistrust.onrender.com/health` y `curl -sS -m 20 https://vitistrust-api.onrender.com/health` → cuál responde (si alguna).

**Step 2 — unificar** la URL viva en los 3 archivos. Si ninguna vive → Task 6.

**Step 3 — revisar cómo llama el frontend:** si los fetch usan `/api/...` (rewrite de Vercel) o `API_BASE` absoluta; dejar UN solo criterio (preferido: `/api` rewrite, mismo origen, CORS ni se dispara en prod).

**Step 4 — verificación E2E:** deploy preview de Vercel → correr una auditoría → llega al backend.

**Step 5 — commit:** `fix(deploy): unify backend URL across vercel.json, frontend fallback and docs`

### Task 6 (condicional): Deploy del backend en Render

Solo si Task 5 descubre que no hay backend vivo.

- Crear `render.yaml` (web service, Python, `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`), commitearlo
- Env vars en Render: `AI_API_KEY`/`GROQ`, `STELLAR_ORACLE_SECRET`, `SOROBAN_CONTRACT_ID`, `HEDERA_*`, `SENTINEL_*`, `CORS_ORIGINS`
- Verificar `/health` 200 + auditoría E2E
- Commit: `chore(deploy): add render.yaml for reproducible backend deploy`

### Task 7: Soroban real — toolchain y contrato compilando

**Step 1:** `rustup update stable` (edition2024 para soroban-sdk 20)
**Step 2:** `cd contracts/vitis_registry && cargo test` → los 4 tests existentes pasan
**Step 3:** `stellar contract build` → WASM generado
**Commit:** `chore(contracts): bump toolchain, green build` (si hubo cambios)

### Task 8: Soroban real — queries y confirmación de tx en el adapter

**Files:** Modify `backend/stellar_adapter.py`

- Implementar `get_vitis_score` / `has_record` (hoy `NotImplementedError`) como simulate/invoke read-only
- Reemplazar el retorno de hash falso (~línea 201) por polling real de confirmación (getTransaction hasta SUCCESS/FAILED, timeout)
- Test de regresión: mock del RPC, verificar que el hash retornado es el de la tx enviada
- Commit: `feat(backend): real soroban queries and tx confirmation polling`

### Task 9: Soroban real — deploy a testnet y wiring

- Crear `scripts/deploy_stellar.py` (referenciado en `agents.md`, no existe) o documentar deploy con stellar-cli
- Deploy → capturar `SOROBAN_CONTRACT_ID` real
- Setearlo en `.env` local + Render
- Verificación: auditoría E2E produce tx hash real visible en stellar.expert testnet; el modal del frontend la muestra
- Commit: `feat(contracts): deploy vitis_registry to stellar testnet + wire contract id`

---

## Verificación final (checklist demo)

- [ ] Auditoría E2E desde la URL pública de Vercel funciona sin errores de consola
- [ ] OracleModal muestra topic Hedera (hashscan) + tx Stellar (stellar.expert), ambos clickeables
- [ ] Backend con Groq apagado devuelve fallback SIN crashear (test manual con key inválida)
- [ ] `pytest` verde en backend/agents; `npm run build` verde en frontend

## Estimación

Tasks 1-4: medio día. Task 5-6: medio día (más si hay que deployar). Tasks 7-9: 1-2 días. Total: 2-3 días enfocados → cómodo dentro de la ventana de 7-10 días para aplicar.

## Fuera de scope (para después)

P1 (cosmética pitch: logo, "s" suelta, v2.0, email, i18n, NDVI sintético), P2 (deuda), y el debate de matar RSK.
