import requests
from typing import Dict, Any
from backend.utils.logger import get_logger

logger = get_logger("nemotron")

class NemotronClient:
    def __init__(self, endpoint: str):
        self.endpoint = endpoint

    def analyze_frame(self, event: Dict[str, Any]) -> Dict[str, Any]:
        # Sends a lightweight request with context and base64 frame path reference
        payload = {
            "prompt": self._build_prompt(event),
            "meta": event.get('meta')
        }
        try:
            r = requests.post(self.endpoint + "/analyze", json=payload, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.error("Nemotron call failed: %s", e)
            return {"error": str(e)}

    def _build_prompt(self, event: Dict[str, Any]) -> str:
        prompt = "You are a security VLM. Analyze the following event for suspicious behavior and produce structured JSON with fields: action, threat_level, objects, recommendations.\n"
        prompt += f"Event metadata: {event.get('meta')}\n"
        prompt += "Look for weapons, fights, loitering, trespassing, abandoned objects, vehicle anomalies, group interactions. Provide short and precise answers."
        return prompt
