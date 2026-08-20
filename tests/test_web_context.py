"""
tests/test_web_context.py
Tests for WebContextAnalyzer: perceptual hashing, local duplicate detection,
fallback behavior, and SerpAPI mock handling.
"""
import pytest
from pathlib import Path
from PIL import Image
from unittest.mock import patch, MagicMock

from app.analyzers.web_context_analyzer import WebContextAnalyzer


@pytest.fixture
def sample_image(tmp_path):
    img = Image.new('RGB', (120, 120), color=(100, 150, 200))
    p = tmp_path / 'sample.jpg'
    img.save(p)
    return p


def test_web_context_analyzer_local_phash(sample_image):
    analyzer = WebContextAnalyzer(serp_api_key='')
    res = analyzer.analyze(sample_image, 'EV-TEST-001')

    assert res['evidence_id'] == 'EV-TEST-001'
    assert res['calibration_status'] == 'UNVALIDATED'
    assert res['phash'] is not None
    assert isinstance(res['phash'], str)
    assert res['dhash'] is not None
    assert res['whash'] is not None
    assert 'disclaimer' in res
    assert res['web_search']['status'] == 'DISABLED'


def test_local_duplicate_detection(sample_image):
    analyzer = WebContextAnalyzer(serp_api_key='')
    # Compute true phash
    raw_res = analyzer._compute_perceptual_hashes(sample_image)
    phash = raw_res['phash']
    assert phash is not None

    existing_hashes = [
        {'evidence_id': 'EV-OLD-001', 'filename': 'original.jpg', 'phash': phash},
        {'evidence_id': 'EV-OTHER-002', 'filename': 'other.jpg', 'phash': 'ffffffffffffffff'},
    ]

    res = analyzer.analyze(sample_image, 'EV-NEW-002', existing_evidence_hashes=existing_hashes)
    dupes = res['local_duplicates']
    assert len(dupes) >= 1
    assert dupes[0]['evidence_id'] == 'EV-OLD-001'
    assert dupes[0]['hamming_distance'] == 0
    assert dupes[0]['similarity_label'] == 'NEAR_DUPLICATE'


def test_serpapi_mock_success(sample_image):
    analyzer = WebContextAnalyzer(serp_api_key='mock_key_123')

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        'visual_matches': [
            {
                'title': 'Original News Photograph 2021',
                'source': 'Reuters',
                'link': 'https://reuters.com/article/123',
                'date': 'Oct 12, 2021',
                'similarity': '0.94'
            }
        ]
    }

    with patch('requests.post', return_value=mock_resp):
        res = analyzer.analyze(sample_image, 'EV-TEST-WEB')
        assert res['web_search']['status'] == 'COMPLETE'
        assert res['web_search']['total_matches'] == 1
        matches = res['web_search']['results']
        assert len(matches) == 1
        assert matches[0]['source'] == 'Reuters'
        assert 'reuters.com' in matches[0]['source_url']


def test_serpapi_mock_error_handling(sample_image):
    analyzer = WebContextAnalyzer(serp_api_key='mock_key_123')

    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.json.return_value = {'error': 'Invalid API Key'}

    with patch('requests.post', return_value=mock_resp):
        res = analyzer.analyze(sample_image, 'EV-TEST-WEB-ERR')
        assert res['web_search']['status'] == 'ERROR'
        assert '401' in res['web_search']['reason']
