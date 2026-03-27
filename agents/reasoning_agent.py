# agents/reasoning_agent.py
import logging
import json
from typing import Any

from groq import Groq, GroqError

from dotenv import load_dotenv
import os

load_dotenv()

logger = logging.getLogger("vitistrust.reasoning")

def analyze_vineyard_health(satellite_data: dict[str, Any]) -> dict[str, Any]:
    api_key = os.getenv("AI_API_KEY")
    model = "llama-3.3-70b-versatile"
    
    if not api_key:
        logger.error("AI_API_KEY not configured")
        return _fallback_verdict("API key not configured")
    
    ndvi = satellite_data.get("ndvi", 0.5)
    score = int(min(100, max(0, int(ndvi * 100))))
    
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
    return {
        "score": 0,
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