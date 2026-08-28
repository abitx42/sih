"""
app/core/sightengine_gateway.py
================================
SightEngine External AI-Generated Image Detection Gateway.
Free tier: 2,000 operations/month.
API docs: https://sightengine.com/docs/
"""
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional
import requests

logger = logging.getLogger(__name__)


class SightEngineGateway:
    """External cross-verification via SightEngine GenAI detection API."""
    
    API_URL = "https://api.sightengine.com/1.0/check.json"
    VERSION = "1.0.0"
    
    @classmethod
    def is_configured(cls) -> bool:
        return bool(os.getenv("SIGHTENGINE_API_USER")) and bool(os.getenv("SIGHTENGINE_API_SECRET"))
    
    @classmethod
    def analyze(cls, file_path: Path, evidence_id: str = "EVIDENCE") -> Dict[str, Any]:
        """Sends image to SightEngine for AI-generation detection."""
        if not cls.is_configured():
            return cls._unavailable_result("SightEngine API credentials not configured")

        from app.core.rate_limiter import ExternalAPIRateLimiter
        if not ExternalAPIRateLimiter.can_call_sightengine():
            return cls._unavailable_result("SightEngine hourly rate limit reached — preserved for investigator quotas")
        
        try:
            api_user = os.getenv("SIGHTENGINE_API_USER")
            api_secret = os.getenv("SIGHTENGINE_API_SECRET")
            
            with open(file_path, 'rb') as f:
                response = requests.post(
                    cls.API_URL,
                    files={'media': (file_path.name, f, 'image/jpeg')},
                    data={
                        'models': 'genai',
                        'api_user': api_user,
                        'api_secret': api_secret
                    },
                    timeout=30
                )
            
            if response.status_code != 200:
                return cls._unavailable_result(f"SightEngine API returned {response.status_code}")
            
            data = response.json()
            
            if data.get('status') != 'success':
                return cls._unavailable_result(f"SightEngine error: {data.get('error', {}).get('message', 'Unknown')}")
            
            ai_generated_score = data.get('type', {}).get('ai_generated', 0.0)
            
            return {
                "source": "SightEngine External API",
                "version": cls.VERSION,
                "evidence_id": evidence_id,
                "available": True,
                "ai_generated_score": round(float(ai_generated_score), 4),
                "ai_indicator": round(float(ai_generated_score), 4),
                "verdict": "AI_GENERATED" if ai_generated_score > 0.5 else "LIKELY_AUTHENTIC",
                "confidence": "HIGH" if (ai_generated_score > 0.8 or ai_generated_score < 0.2) else "MEDIUM",
                "raw_response": data
            }
            
        except requests.exceptions.Timeout:
            return cls._unavailable_result("SightEngine API request timed out")
        except requests.exceptions.ConnectionError:
            return cls._unavailable_result("Could not connect to SightEngine API")
        except Exception as e:
            logger.error(f"SightEngine analysis error for {evidence_id}: {e}")
            return cls._unavailable_result(str(e))
    
    @classmethod
    def _unavailable_result(cls, reason: str) -> Dict[str, Any]:
        return {
            "source": "SightEngine External API",
            "version": cls.VERSION,
            "available": False,
            "ai_generated_score": None,
            "ai_indicator": None,
            "verdict": "EXTERNAL_UNAVAILABLE",
            "reason": reason
        }
