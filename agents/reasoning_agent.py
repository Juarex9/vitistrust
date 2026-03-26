# agents/reasoning_agent.py
import logging
import json
from typing import Any

from groq import Groq, GroqError

from dotenv import load_dotenv
import os

load_dotenv()

logger = logging.getLogger("vitistrust.reasoning")

DEFAULT_MODEL = "llama-3.3-70b-versatile"


def analyze_vineyard_health(satellite_data: dict[str, Any]) -> dict[str, Any]:
    """
    Analiza datos satelitales y emite un veredicto usando DeepSeek-R1.
    
    Args:
        satellite_data: Dict con datos del perception_agent (ndvi, coordinates, etc)
        
    Returns:
        Dict con score (0-100), risk_level, justification
    """
    api_key = os.getenv("AI_API_KEY")
    # Force using llama-3.3-70b as it's the latest available model
    model = "llama-3.3-70b-versatile"
    
    if not api_key:
        logger.error("AI_API_KEY not configured")
        return _fallback_verdict("API key not configured")
    
    prompt = f"""
Actúa como un experto agrónomo de Mendoza, Argentina. 
Analiza los siguientes datos satelitales de un viñedo:
{json.dumps(satellite_data, indent=2)}

TAREA:
1. Calcula un 'VitisScore' de 0 a 100 basado en el NDVI (Normal: 0.4 - 0.9).
2. Identifica riesgos (heladas, sequía, nubes).
3. Redacta una justificación técnica breve (2 frases).
4. Devuelve el resultado ESTRICTAMENTE en formato JSON con las llaves: 
   'score', 'risk_level', 'justification'.
"""
    try:
        client = Groq(api_key=api_key)
        
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(chat_completion.choices[0].message.content)
        
        logger.info(f"VitisScore: {result.get('score')}, Risk: {result.get('risk_level')}")
        return result
        
    except GroqError as e:
        logger.error(f"Groq API error: {e}")
        return _fallback_verdict(f"AI API error: {str(e)}")
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse AI response: {e}")
        return _fallback_verdict("Invalid AI response format")
    except Exception as e:
        logger.error(f"Unexpected error in reasoning: {e}")
        return _fallback_verdict(str(e))


def _fallback_verdict(error_msg: str) -> dict[str, Any]:
    """Fallback verdict when AI fails."""
    return {
        "score": 0,
        "risk_level": "UNKNOWN",
        "justification": f"Error en análisis: {error_msg}"
    }


if __name__ == "__main__":
    mock_sat_data = {
        "ndvi": 0.75,
        "status": "success",
        "coordinates": {"lat": -33.125, "lon": -68.895}
    }
    print("Analyzing vineyard...")
    verdict = analyze_vineyard_health(mock_sat_data)
    print(json.dumps(verdict, indent=2))