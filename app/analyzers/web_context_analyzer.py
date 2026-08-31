"""
app/analyzers/web_context_analyzer.py
Web Context & Perceptual Hash Provenance Analyzer.
"""
import logging, time
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

try:
    import imagehash
    from PIL import Image as _PILImage
    _IMAGEHASH_AVAILABLE = True
except ImportError:
    _IMAGEHASH_AVAILABLE = False
    logger.info("imagehash not installed. Run: pip install imagehash")


class WebContextAnalyzer:
    CALIBRATION_STATUS = "UNVALIDATED"
    _PHASH_NEAR_DUPLICATE_THRESHOLD = 8
    _PHASH_SIMILAR_THRESHOLD = 14

    def __init__(self, serp_api_key: str = ""):
        self.serp_api_key = serp_api_key.strip()

    def analyze(self, image_path: Path, evidence_id: str, existing_evidence_hashes: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        t0 = time.time()
        result: Dict[str, Any] = {
            "evidence_id": evidence_id,
            "calibration_status": self.CALIBRATION_STATUS,
            "disclaimer": ("Web context signals are investigator leads only. A web match does NOT prove manipulation. No match does NOT prove authenticity."),
        }
        phash_result = self._compute_perceptual_hashes(image_path)
        result.update(phash_result)
        if phash_result.get("phash") and existing_evidence_hashes:
            result["local_duplicates"] = self._find_local_duplicates(phash_result["phash"], existing_evidence_hashes, exclude_id=evidence_id)
        else:
            result["local_duplicates"] = []
        if self.serp_api_key and phash_result.get("phash_error") is None:
            result["web_search"] = self._search_serpapi(image_path, evidence_id)
        else:
            reason = "SERP_API_KEY not configured" if not self.serp_api_key else "pHash unavailable"
            result["web_search"] = {"status": "DISABLED", "reason": f"Optional web search not active: {reason}. Add SERP_API_KEY to .env to enable.", "results": []}
        result["status"] = "COMPLETE" if _IMAGEHASH_AVAILABLE else "PARTIAL"
        result["latency_ms"] = round((time.time() - t0) * 1000, 1)
        return result

    def _compute_perceptual_hashes(self, image_path: Path) -> Dict[str, Any]:
        if not _IMAGEHASH_AVAILABLE:
            return {"phash": None, "dhash": None, "whash": None, "phash_error": "imagehash not installed"}
        try:
            with _PILImage.open(image_path) as raw_img:
                img = raw_img.convert("RGB")
                return {"phash": str(imagehash.phash(img)), "dhash": str(imagehash.dhash(img)), "whash": str(imagehash.whash(img)), "phash_error": None}
        except Exception as e:
            logger.warning(f"Perceptual hash failed for {image_path}: {e}")
            return {"phash": None, "dhash": None, "whash": None, "phash_error": str(e)}

    def _find_local_duplicates(self, phash_str: str, existing_hashes: List[Dict[str, Any]], exclude_id: str) -> List[Dict[str, Any]]:
        if not _IMAGEHASH_AVAILABLE:
            return []
        try:
            query_hash = imagehash.hex_to_hash(phash_str)
        except Exception:
            return []
        duplicates = []
        for entry in existing_hashes:
            eid = entry.get("evidence_id", "")
            stored_phash = entry.get("phash")
            if not stored_phash or eid == exclude_id:
                continue
            try:
                distance = query_hash - imagehash.hex_to_hash(stored_phash)
                if distance <= self._PHASH_SIMILAR_THRESHOLD:
                    label = "NEAR_DUPLICATE" if distance <= self._PHASH_NEAR_DUPLICATE_THRESHOLD else "VISUALLY_SIMILAR"
                    duplicates.append({"evidence_id": eid, "filename": entry.get("filename", "unknown"), "hamming_distance": distance, "similarity_label": label, "note": "Investigator lead — verify provenance manually."})
            except Exception:
                continue
        duplicates.sort(key=lambda x: x["hamming_distance"])
        return duplicates

    def _search_serpapi(self, image_path: Path, evidence_id: str) -> Dict[str, Any]:
        try:
            import requests
        except ImportError:
            return {"status": "ERROR", "reason": "requests unavailable", "results": []}
        try:
            url = "https://serpapi.com/search"
            with open(image_path, "rb") as f:
                files = {"image": (image_path.name, f, "image/jpeg")}
                params = {"engine": "google_lens", "api_key": self.serp_api_key}
                resp = requests.post(url, params=params, files=files, timeout=15)
            if resp.status_code != 200:
                return {"status": "ERROR", "reason": f"SerpAPI HTTP {resp.status_code}", "results": []}
            data = resp.json()
            results = [{"title": m.get("title",""), "source": m.get("source",""), "source_url": m.get("link",""), "date_published": m.get("date",""), "similarity": m.get("similarity","")} for m in data.get("visual_matches",[])[:8]]
            return {"status": "COMPLETE", "engine": "Google Lens via SerpAPI", "total_matches": len(results), "results": results, "disclaimer": "Web matches are investigator leads only."}
        except Exception as e:
            logger.warning(f"SerpAPI search failed for {evidence_id}: {e}")
            return {"status": "ERROR", "reason": str(e), "results": []}
