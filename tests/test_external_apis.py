"""
tests/test_external_apis.py
Tests for SightEngine, Reverse Image Search, and Copilot fallback.
"""
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from app.core.sightengine_gateway import SightEngineGateway
from app.core.reverse_image_search import ReverseImageSearch
from app.core.copilot import ForensicCopilot
from app.config import settings

def test_sightengine_unavailable_without_credentials():
    with patch.dict(os.environ, clear=True):
        result = SightEngineGateway.analyze(Path("dummy.jpg"))
        assert result["available"] is False
        assert result["verdict"] == "EXTERNAL_UNAVAILABLE"

def test_reverse_image_search_unavailable_without_credentials():
    with patch.dict(os.environ, clear=True):
        result = ReverseImageSearch.analyze(Path("dummy.jpg"))
        assert result["available"] is False
        assert result["reason"] == "Google Cloud Vision API credentials not configured"

@patch("app.core.copilot.requests.post")
def test_copilot_fallback_chain(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": '{"investigator_summary": "Test Summary", "technical_findings_requiring_review": [], "limitations": "", "recommended_next_steps": []}'
                }
            }
        ]
    }
    mock_post.return_value = mock_response

    # Force settings so that we only test Groq
    original_api_key = settings.LLM_API_KEY
    original_base_url = settings.LLM_API_BASE_URL
    settings.LLM_API_KEY = ""
    settings.LLM_API_BASE_URL = ""
    
    with patch.dict(os.environ, {"GROQ_API_KEY": "test_groq"}):
        result = ForensicCopilot.generate_structured_explanation(
            evidence_id="EVIDENCE_1",
            evidence_data={},
            forensic_result={},
            findings=[]
        )
        
        assert result is not None
        assert result.get("source") == "Groq (llama3-8b-8192)"
        assert result.get("investigator_summary") == "Test Summary"
        
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://api.groq.com/openai/v1/chat/completions"

    # Restore settings
    settings.LLM_API_KEY = original_api_key
    settings.LLM_API_BASE_URL = original_base_url

def test_copilot_deterministic_fallback():
    # If all fail or aren't configured, should fall back to deterministic
    original_api_key = settings.LLM_API_KEY
    original_base_url = settings.LLM_API_BASE_URL
    settings.LLM_API_KEY = ""
    settings.LLM_API_BASE_URL = ""
    
    with patch.dict(os.environ, {}, clear=True):
        result = ForensicCopilot.generate_structured_explanation(
            evidence_id="EVIDENCE_2",
            evidence_data={"original_filename": "test.jpg", "modality": "IMAGE"},
            forensic_result={"forensic_risk_score": 10, "risk_category": "LOW RISK"},
            findings=[]
        )
        
        assert result is not None
        assert result.get("source") == "Local Deterministic Engine"
        assert "LOW RISK" in result.get("investigator_summary")

    # Restore settings
    settings.LLM_API_KEY = original_api_key
    settings.LLM_API_BASE_URL = original_base_url
