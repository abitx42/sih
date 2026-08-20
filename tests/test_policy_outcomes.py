"""
tests/test_policy_outcomes.py
==============================
Tests ensuring compliance of policy outcomes with benchmark structure definitions.
"""
import json
from pathlib import Path
import pytest
from app.core.localization_policy import (
    OUTCOME_VERIFIED_PROVENANCE,
    OUTCOME_REFERENCE_DIFFERENCE_CONFIRMED,
    OUTCOME_LOCALIZED_ANOMALY_REQUIRING_REVIEW,
    OUTCOME_GENERATIVE_IMAGE_INDICATOR,
    OUTCOME_INCONCLUSIVE,
    OUTCOME_NO_STRONG_INDICATOR_FOUND,
)


def test_benchmark_structure_file_valid():
    bench_file = Path("benchmarks/benchmark_structure.json")
    assert bench_file.exists(), "benchmark_structure.json must exist"
    
    with open(bench_file, "r") as f:
        data = json.load(f)
        
    assert "benchmark_categories" in data
    cats = data["benchmark_categories"]
    required_cats = {"pristine", "manual_edit", "ai_inpaint", "fully_generated", "recompressed"}
    assert required_cats.issubset(set(cats.keys())), f"Missing categories: {required_cats - set(cats.keys())}"
    
    valid_outcomes = {
        OUTCOME_VERIFIED_PROVENANCE,
        OUTCOME_REFERENCE_DIFFERENCE_CONFIRMED,
        OUTCOME_LOCALIZED_ANOMALY_REQUIRING_REVIEW,
        OUTCOME_GENERATIVE_IMAGE_INDICATOR,
        OUTCOME_INCONCLUSIVE,
        OUTCOME_NO_STRONG_INDICATOR_FOUND,
    }

    
    for cat_name, cat_info in cats.items():
        assert "expected_policy_outcomes" in cat_info
        for outcome in cat_info["expected_policy_outcomes"]:
            assert outcome in valid_outcomes, f"Invalid outcome {outcome} in category {cat_name}"


def test_no_unsupported_accuracy_claims_in_benchmark():
    bench_file = Path("benchmarks/benchmark_structure.json")
    with open(bench_file, "r") as f:
        content = f.read()
    # Check that no fake percentage accuracy claims exist
    assert "99." not in content
    assert "98." not in content
    assert "100%" not in content
