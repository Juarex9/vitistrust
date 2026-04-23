# agents/reasoning_agent.py
import logging
import json
from typing import Any

from groq import Groq, GroqError

from dotenv import load_dotenv
import os

load_dotenv()

logger = logging.getLogger("vitistrust.reasoning")

SCORE_MODEL_VERSION = "v1.0.0"
SCORE_WEIGHTS = {
    "vegetation": 0.35,
    "humidity": 0.20,
    "temporal_consistency": 0.15,
    "data_quality": 0.15,
    "regional_benchmark": 0.15,
}


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _compute_score_breakdown(satellite_data: dict[str, Any]) -> dict[str, Any]:
    """
    Modelo transparente de score con pesos explícitos.

    Componentes (0-1):
    - Vegetation: usa NDVI.
    - Humidity: usa NDMI si existe; fallback desde NDVI.
    - Temporal consistency: estabilidad temporal (ndvi_trend/historical_consistency).
    - Data quality: cobertura de nubes + completitud de campos.
    - AI reliability: confianza del pipeline IA (ok/error/fallback).
    """
    ndvi = float(satellite_data.get("ndvi", 0.0))
    ndmi = satellite_data.get("ndmi")
    cloud_coverage = float(satellite_data.get("cloud_coverage", 20.0))
    source = str(satellite_data.get("source", "unknown")).lower()
    status = str(satellite_data.get("status", "unknown")).lower()
    historical_consistency = satellite_data.get("historical_consistency")
    ndvi_trend = str(satellite_data.get("ndvi_trend", "stable")).lower()

    vegetation = _clamp01((ndvi + 0.2) / 1.1)

    if ndmi is not None:
        humidity = _clamp01((float(ndmi) + 0.4) / 1.0)
    else:
        humidity = _clamp01(0.25 + 0.75 * _clamp01(ndvi))

    if historical_consistency is not None:
        temporal_consistency = _clamp01(float(historical_consistency))
    else:
        trend_map = {"improving": 0.80, "stable": 0.72, "declining": 0.45, "volatile": 0.35}
        temporal_consistency = trend_map.get(ndvi_trend, 0.60)

    cloud_factor = _clamp01(1 - (cloud_coverage / 100))
    required_fields = ["ndvi", "coordinates", "source", "status"]
    completeness = sum(1 for field in required_fields if field in satellite_data) / len(required_fields)
    source_factor = 1.0 if "sentinel" in source else 0.85 if source != "unknown" else 0.70
    data_quality = _clamp01((0.5 * cloud_factor) + (0.3 * completeness) + (0.2 * source_factor))

    ai_reliability = 0.90 if status == "success" else 0.60 if status == "partial" else 0.40

    # Benchmark regional: comparar NDVI con promedio de la zona
    region_avg_ndvi = satellite_data.get("regional_avg_ndvi")
    if region_avg_ndvi is not None:
        ndvi_diff = ndvi - region_avg_ndvi
        if ndvi_diff > 0.1:
            regional_benchmark = 1.0  # Por encima del promedio
        elif ndvi_diff > -0.1:
            regional_benchmark = 0.8  # En línea con el promedio
        elif ndvi_diff > -0.2:
            regional_benchmark = 0.5  # Bajo el promedio
        else:
            regional_benchmark = 0.2  # Muy bajo
    else:
        regional_benchmark = 0.7  # Sin datos regionales, neutral

    components = {
        "vegetation": vegetation,
        "humidity": humidity,
        "temporal_consistency": temporal_consistency,
        "data_quality": data_quality,
        "regional_benchmark": regional_benchmark,
    }

    details = {}
    total_score = 0
    for key, value in components.items():
        weight = SCORE_WEIGHTS[key]
        contribution = round(value * weight * 100, 2)
        total_score += contribution
        details[key] = {
            "weight": weight,
            "component_score": round(value * 100, 2),
            "contribution": contribution,
        }

    return {
        "score_model_version": SCORE_MODEL_VERSION,
        "weights": SCORE_WEIGHTS,
        "components": details,
        "total_score": int(round(total_score)),
    }

def analyze_vineyard_health(satellite_data: dict[str, Any]) -> dict[str, Any]:
    api_key = os.getenv("AI_API_KEY")
    model = "llama-3.3-70b-versatile"
    
    if not api_key:
        logger.error("AI_API_KEY not configured")
        return _fallback_verdict("API key not configured")
    
    ndvi = float(satellite_data.get("ndvi", 0.5))
    score_breakdown = _compute_score_breakdown(satellite_data)
    score = score_breakdown["total_score"]
    
    if ndvi > 0.7:
        risk_level, risk_score, recommendation = "low", 20, "BUY"
        health_status = "healthy"
    elif ndvi > 0.5:
        risk_level, risk_score, recommendation = "medium", 50, "HOLD"
        health_status = "moderate"
    elif ndvi > 0.3:
        risk_level, risk_score, recommendation = "high", 75, "SELL"
        health_status = "stressed"
    else:
        risk_level, risk_score, recommendation = "high", 90, "SELL"
        health_status = "critical"
    
    yield_forecast = "10-12 tons/ha" if ndvi > 0.6 else "6-8 tons/ha" if ndvi > 0.4 else "3-5 tons/ha"
    confidence = "high" if ndvi > 0.6 else "medium" if ndvi > 0.4 else "low"
    price_trend = "stable" if ndvi > 0.5 else "declining"
    
    prompt = f"""
Eres un experto agrónomo especializado en viñedos de Mendoza, Argentina.

Analiza los siguientes datos satelitales:
- NDVI: {ndvi}
- Coordinates: {satellite_data.get('coordinates', {})}
- Source: {satellite_data.get('source', 'unknown')}

Proporciona un análisis de inversión en JSON:
{{
  "risk_factors": ["factor1", "factor2"],
  "threats": [{{"type": "x", "severity": "low", "mitigation": "y"}}],
  "justification": "2-3 sentences in Spanish"
}}
"""
    try:
        client = Groq(api_key=api_key)
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            response_format={"type": "json_object"}
        )
        
        ai_result = json.loads(chat_completion.choices[0].message.content)
        
        normalized_threats = []
        for t in ai_result.get("threats", []):
            sev = t.get("severity", "medium")
            sev_norm = "low" if sev in ["baja", "low", "bajo"] else "high" if sev in ["alta", "high", "alto"] else "medium"
            normalized_threats.append({
                "type": t.get("type", "unknown"),
                "severity": sev_norm,
                "mitigation": t.get("mitigation", "N/A")
            })
        
        return {
            "score": score,
            "score_model_version": SCORE_MODEL_VERSION,
            "score_breakdown": score_breakdown,
            "risk_level": risk_level,
            "justification": ai_result.get("justification", f"Viñedo en estado {health_status}. NDVI: {ndvi:.3f}"),
            "investment_analysis": {
                "risk_score": risk_score,
                "risk_factors": ai_result.get("risk_factors", ["ndvi_stress"]),
                "recommendation": recommendation,
                "yield_forecast": yield_forecast,
                "confidence": confidence,
                "price_trend": price_trend,
                "threats": normalized_threats
            },
            "metrics": {
                "ndvi_trend": "stable",
                "vegetation_coverage": round(ndvi, 2),
                "stress_indicators": ["low_precipitation"] if ndvi < 0.5 else []
            }
        }
    except (GroqError, json.JSONDecodeError, Exception) as e:
        logger.error(f"AI analysis failed: {e}")
        return _fallback_verdict(str(e))

def _fallback_verdict(error_msg: str) -> dict[str, Any]:
    score_breakdown = {
        "score_model_version": SCORE_MODEL_VERSION,
        "weights": SCORE_WEIGHTS,
        "components": {
            "vegetation": {"weight": SCORE_WEIGHTS["vegetation"], "component_score": 0.0, "contribution": 0.0},
            "humidity": {"weight": SCORE_WEIGHTS["humidity"], "component_score": 0.0, "contribution": 0.0},
            "temporal_consistency": {"weight": SCORE_WEIGHTS["temporal_consistency"], "component_score": 0.0, "contribution": 0.0},
            "data_quality": {"weight": SCORE_WEIGHTS["data_quality"], "component_score": 0.0, "contribution": 0.0},
            "ai_reliability": {"weight": SCORE_WEIGHTS["ai_reliability"], "component_score": 0.0, "contribution": 0.0},
        },
        "total_score": 0,
    }
    return {
        "score": 0,
        "score_model_version": SCORE_MODEL_VERSION,
        "score_breakdown": score_breakdown,
        "risk_level": "UNKNOWN",
        "justification": f"Error en análisis: {error_msg}",
        "investment_analysis": {
            "risk_score": 100,
            "risk_factors": ["analysis_unavailable"],
            "recommendation": "SELL",
            "yield_forecast": "Unable to analyze",
            "confidence": "low",
            "price_trend": "unknown",
            "threats": [{"type": "system_error", "severity": "high", "mitigation": "Retry verification"}]
        },
        "metrics": {"ndvi_trend": "unknown", "vegetation_coverage": 0, "stress_indicators": ["analysis_failed"]}
    }

if __name__ == "__main__":
    print(analyze_vineyard_health({"ndvi": 0.75, "status": "success", "coordinates": {"lat": -33.125, "lon": -68.895}}))
