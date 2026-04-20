# VitisScore Model (Version v1.0.0)

## Objetivo
Definir una fórmula **transparente, reproducible y auditable** para calcular el VitisScore (0-100) a partir de cinco dimensiones:

1. Vegetación
2. Humedad
3. Consistencia temporal
4. Calidad de datos
5. Confiabilidad de IA

## Versión del modelo
- `score_model_version = "v1.0.0"`
- Implementación de referencia: `agents/reasoning_agent.py`.

## Fórmula general

\[
\text{VitisScore} = \sum_{i=1}^{5} \left(w_i \cdot c_i\right) \cdot 100
\]

Donde:
- \(w_i\) = peso del componente \(i\)
- \(c_i\) = score normalizado del componente \(i\) en rango \([0, 1]\)

### Pesos (deben sumar 1.0)

| Componente | Símbolo | Peso |
|---|---:|---:|
| Vegetación | `w_veg` | 0.35 |
| Humedad | `w_hum` | 0.20 |
| Consistencia temporal | `w_tmp` | 0.15 |
| Calidad de datos | `w_qual` | 0.15 |
| Confiabilidad IA | `w_ai` | 0.15 |

## Definición de componentes

### 1) Vegetación (`c_veg`)
- Entrada principal: `ndvi`
- Normalización:

\[
c_{veg} = clamp\left(\frac{ndvi + 0.2}{1.1}, 0, 1\right)
\]

### 2) Humedad (`c_hum`)
- Si existe `ndmi`:

\[
c_{hum} = clamp\left(\frac{ndmi + 0.4}{1.0}, 0, 1\right)
\]

- Si no existe `ndmi` (fallback):

\[
c_{hum} = clamp\left(0.25 + 0.75 \cdot clamp(ndvi,0,1), 0, 1\right)
\]

### 3) Consistencia temporal (`c_tmp`)
- Prioridad 1: `historical_consistency` en \([0,1]\)
- Prioridad 2: mapeo cualitativo por `ndvi_trend`
  - `improving` → 0.80
  - `stable` → 0.72
  - `declining` → 0.45
  - `volatile` → 0.35
  - otro valor → 0.60

### 4) Calidad de datos (`c_qual`)
Se compone de tres subfactores:
- `cloud_factor = 1 - cloud_coverage/100`
- `completeness = campos_presentes / campos_requeridos`
  - Campos requeridos: `ndvi`, `coordinates`, `source`, `status`
- `source_factor`
  - 1.0 si fuente contiene `sentinel`
  - 0.85 si fuente conocida (no `unknown`)
  - 0.70 si `unknown`

Combinación:

\[
c_{qual} = clamp\left(0.5\cdot cloud\_factor + 0.3\cdot completeness + 0.2\cdot source\_factor, 0, 1\right)
\]

### 5) Confiabilidad IA (`c_ai`)
Basada en `status` del pipeline de datos:
- `success` → 0.90
- `partial` → 0.60
- otro valor / error → 0.40

## Estructura de salida requerida
El backend debe exponer:
- `score_model_version`
- `score_breakdown`

Formato esperado:

```json
{
  "score_model_version": "v1.0.0",
  "weights": {
    "vegetation": 0.35,
    "humidity": 0.20,
    "temporal_consistency": 0.15,
    "data_quality": 0.15,
    "ai_reliability": 0.15
  },
  "components": {
    "vegetation": {"weight": 0.35, "component_score": 72.3, "contribution": 25.31},
    "humidity": {"weight": 0.20, "component_score": 66.0, "contribution": 13.2}
  },
  "total_score": 74
}
```

## Reglas de versionado
- Cambios en pesos, normalización o mapeos cualitativos: **incrementar versión**.
- Cambios de forma:
  - Bugfix no funcional: patch (`v1.0.1`)
  - Ajustes calibrados de fórmula: minor (`v1.1.0`)
  - Cambio incompatible de estructura o semántica: major (`v2.0.0`)
