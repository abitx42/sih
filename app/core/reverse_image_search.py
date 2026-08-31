"""
app/core/reverse_image_search.py
================================
Reverse Image Search Module for Truth Lens.
Supports Google Cloud Vision web_detection and fallback check.
"""
import logging
import os
from pathlib import Path
from typing import Dict, Any
import requests
import base64
import json

logger = logging.getLogger(__name__)

class ReverseImageSearch:
    """Reverse image search integration."""

    KNOWN_AI_PLATFORMS = ["civitai.com", "lexica.art", "deviantart.com/tag/ai", "midjourney.com"]

    @classmethod
    def is_configured(cls) -> bool:
        return bool(os.getenv("GOOGLE_CLOUD_VISION_KEY"))

    @classmethod
    def analyze(cls, file_path: Path, evidence_id: str = "EVIDENCE") -> Dict[str, Any]:
        """Performs reverse image search."""
        if not cls.is_configured():
            return cls._unavailable_result("Google Cloud Vision API credentials not configured")
        
        from app.core.rate_limiter import ExternalAPIRateLimiter
        if not ExternalAPIRateLimiter.can_call_google_vision():
            return cls._unavailable_result("Google Cloud Vision hourly rate limit reached — preserved for investigator quotas")
        
        try:
            api_key = os.getenv("GOOGLE_CLOUD_VISION_KEY")
            url = f"https://vision.googleapis.com/v1/images:annotate?key={api_key}"
            
            with open(file_path, "rb") as f:
                content = f.read()
            
            image_b64 = base64.b64encode(content).decode("utf-8")
            
            payload = {
                "requests": [
                    {
                        "image": {"content": image_b64},
                        "features": [{"type": "WEB_DETECTION"}]
                    }
                ]
            }
            
            response = requests.post(url, json=payload, timeout=30)
            
            if response.status_code != 200:
                return cls._unavailable_result(f"Google Vision API returned {response.status_code}")
                
            data = response.json()
            web_detection = data.get("responses", [{}])[0].get("webDetection", {})
            
            web_entities = [e.get("description") for e in web_detection.get("webEntities", []) if "description" in e]
            matching_pages = [p.get("url") for p in web_detection.get("pagesWithMatchingImages", []) if "url" in p]
            similar_images = [i.get("url") for i in web_detection.get("visuallySimilarImages", []) if "url" in i]
            
            ai_platform_hit = any(platform in page_url for page_url in matching_pages for platform in cls.KNOWN_AI_PLATFORMS)
            
            return {
                "source": "Reverse Image Search",
                "available": True,
                "evidence_id": evidence_id,
                "web_entities": web_entities[:10],
                "matching_pages": matching_pages[:10],
                "visually_similar_images": similar_images[:10],
                "ai_platform_hit": ai_platform_hit
            }

        except requests.exceptions.Timeout:
            return cls._unavailable_result("Reverse image search timed out", evidence_id)
        except requests.exceptions.ConnectionError:
            return cls._unavailable_result("Could not connect to reverse image search API", evidence_id)
        except Exception as e:
            logger.error(f"Reverse image search error for {evidence_id}: {e}")
            return cls._unavailable_result(str(e), evidence_id)
    
    @classmethod
    def _unavailable_result(cls, reason: str, evidence_id: str = "") -> Dict[str, Any]:
        return {
            "source": "Reverse Image Search",
            "available": False,
            "evidence_id": evidence_id,
            "web_entities": [],
            "matching_pages": [],
            "visually_similar_images": [],
            "ai_platform_hit": False,
            "reason": reason
        }
