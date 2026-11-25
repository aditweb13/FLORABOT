"""
Automated Unit and Integration Test Suite for FloraBOT Phase 3:
1. Quality Screening Metrics & Algorithmic Focus Blur (Laplacian variance)
2. Quality Gating against Dark (underexposed), Glare (overexposed), and Low-contrast frames
3. Honest Inconclusive Pipeline Response (Quality rejection handling)
4. Full Benchmark Baseline Evaluation (Evaluation report verification)
"""

import sys
import os
import json
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.vision_engine import assess_image_quality, analyze_plant_image
from evaluate_vision_baseline import run_vision_benchmark

BENCHMARK_DIR = backend_dir / "data" / "benchmark_dataset"

def test_sharp_image_assessment():
    print("Testing assess_image_quality with sharp healthy leaf...")
    sharp_img = str(BENCHMARK_DIR / "sharp_healthy.jpg")
    res = assess_image_quality(sharp_img)
    assert res["is_suitable"] is True, f"Sharp image should be suitable: {res}"
    assert res["blur_score"] > 3.0, f"Sharp image blur score should exceed threshold: {res['blur_score']}"
    assert res["exposure_status"] == "normal", f"Exposure should be normal: {res['exposure_status']}"
    assert len(res["issues"]) == 0, f"Expected 0 issues, got {res['issues']}"
    print("  -> Passed sharp image test.")

def test_blurry_image_rejection():
    print("Testing assess_image_quality with blurred image...")
    blurry_img = str(BENCHMARK_DIR / "blurry_rejected.jpg")
    res = assess_image_quality(blurry_img)
    assert res["is_suitable"] is False, f"Blurry image must be rejected: {res}"
    assert res["is_blurry"] is True, f"is_blurry flag must be True"
    assert "blurry" in res["rejection_reason"].lower(), f"Rejection reason should mention blur: {res['rejection_reason']}"
    print("  -> Passed blurry image rejection test.")

def test_underexposed_image_rejection():
    print("Testing assess_image_quality with underexposed image...")
    dark_img = str(BENCHMARK_DIR / "dark_rejected.jpg")
    res = assess_image_quality(dark_img)
    assert res["is_suitable"] is False, f"Dark image must be rejected: {res}"
    assert res["exposure_status"] == "underexposed"
    assert "underexposure" in res["rejection_reason"].lower() or "dark" in res["rejection_reason"].lower()
    print("  -> Passed underexposed image rejection test.")

def test_overexposed_image_rejection():
    print("Testing assess_image_quality with overexposed glare image...")
    glare_img = str(BENCHMARK_DIR / "glare_rejected.jpg")
    res = assess_image_quality(glare_img)
    assert res["is_suitable"] is False, f"Glare image must be rejected: {res}"
    assert res["exposure_status"] == "overexposed"
    assert "overexposure" in res["rejection_reason"].lower() or "glare" in res["rejection_reason"].lower()
    print("  -> Passed overexposed image rejection test.")

def test_quality_gate_inconclusive_flow():
    print("Testing analyze_plant_image honest inconclusive result on blurry image...")
    blurry_img = str(BENCHMARK_DIR / "blurry_rejected.jpg")
    analysis = analyze_plant_image(blurry_img, plant_hint="Monstera Deliciosa")
    
    assert analysis["disease_detected"] == "uncertain", f"Expected uncertain, got {analysis['disease_detected']}"
    assert analysis["health_status"] == "Image needs a clearer view", f"Expected 'Image needs a clearer view', got {analysis['health_status']}"
    assert analysis["severity"] == "Unassessed", f"Expected Unassessed, got {analysis['severity']}"
    assert "image_quality" in analysis, "image_quality dictionary must be returned"
    assert analysis["image_quality"]["is_suitable"] is False
    assert "quality screening check rejected" in analysis["symptoms"].lower()
    print("  -> Passed honest inconclusive flow test.")

def test_benchmark_baseline_evaluation():
    print("Testing evaluate_vision_baseline.py benchmark execution...")
    report = run_vision_benchmark()
    assert report["dataset_size"] >= 7
    assert report["quality_gate"]["accuracy"] == 1.0, f"Quality gate accuracy should be 100%: {report['quality_gate']['accuracy']}"
    assert report["quality_gate"]["rejection_rate"] > 0.40, f"Rejection rate should reflect unanalyzable samples: {report['quality_gate']['rejection_rate']}"
    assert report["performance"]["accuracy"] == 1.0, f"Disease detection accuracy should be 100%: {report['performance']['accuracy']}"
    assert report["performance"]["precision"] == 1.0
    assert report["performance"]["recall"] == 1.0
    assert report["performance"]["f1_score"] == 1.0
    print("  -> Passed benchmark baseline evaluation test.")

def main():
    print("\n========================================================")
    print("  FLORABOT PHASE 3 TEST SUITE (VISION & QUALITY GATE)")
    print("========================================================\n")
    test_sharp_image_assessment()
    test_blurry_image_rejection()
    test_underexposed_image_rejection()
    test_overexposed_image_rejection()
    test_quality_gate_inconclusive_flow()
    test_benchmark_baseline_evaluation()
    print("\n========================================================")
    print("  ALL PHASE 3 TESTS COMPLETED AND VERIFIED SUCCESSFULLY!")
    print("========================================================\n")

if __name__ == "__main__":
    main()
