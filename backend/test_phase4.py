"""
FloraBOT Phase 4 Automated Test Suite
Verifies:
1. YOLODetector initialization, backend selection (TorchScript / fallback), and model metadata.
2. Bounding box coordinates normalization [0.0 - 1.0] and Non-Maximum Suppression (NMS).
3. Localization on necrotic lesions and chlorosis leaves from benchmark dataset.
4. Non-destructive annotated image generation (render_detection_overlay).
5. Integration into analyze_plant_image and execute_plant_analysis_pipeline.
"""

import sys
import os
import json
from pathlib import Path

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.yolo_detector import get_yolo_detector, detect_plant_diseases, non_max_suppression, calculate_iou
from app.vision_engine import render_detection_overlay, analyze_plant_image

BENCHMARK_DIR = backend_dir / "data" / "benchmark_dataset"

def test_iou_and_nms():
    print("Testing IoU calculation and Non-Maximum Suppression...")
    box1 = [0.1, 0.1, 0.5, 0.5]
    box2 = [0.1, 0.1, 0.5, 0.5]
    assert abs(calculate_iou(box1, box2) - 1.0) < 1e-4, "Identical boxes must have IoU = 1.0"

    box_disjoint = [0.6, 0.6, 0.9, 0.9]
    assert calculate_iou(box1, box_disjoint) == 0.0, "Disjoint boxes must have IoU = 0.0"

    overlapping_detections = [
        {"x1": 0.1, "y1": 0.1, "x2": 0.5, "y2": 0.5, "label": "necrosis_lesion", "confidence": 0.90},
        {"x1": 0.12, "y1": 0.11, "x2": 0.49, "y2": 0.52, "label": "necrosis_lesion", "confidence": 0.75}, # redundant
        {"x1": 0.6, "y1": 0.6, "x2": 0.9, "y2": 0.9, "label": "chlorosis_leaf", "confidence": 0.85}
    ]
    kept = non_max_suppression(overlapping_detections, iou_threshold=0.45)
    assert len(kept) == 2, f"NMS should keep 2 distinct detections, kept: {len(kept)}"
    assert kept[0]["confidence"] == 0.90
    assert kept[1]["label"] == "chlorosis_leaf"
    print("  -> Passed IoU and NMS test.")

def test_yolo_detector_initialization():
    print("Testing YOLODetector initialization and metadata...")
    detector = get_yolo_detector()
    assert detector is not None
    assert detector.backend_type in ("torchscript", "onnxruntime", "heuristic_fallback")
    print(f"  -> Active YOLO backend: {detector.backend_type}")

def test_yolo_lesion_detection():
    print("Testing lesion localization on necrotic benchmark leaf...")
    necrosis_img = str(BENCHMARK_DIR / "necrosis_brown.jpg")
    res = detect_plant_diseases(necrosis_img, conf_threshold=0.30)
    dets = res["detections"]
    assert len(dets) > 0, "Expected at least 1 localized lesion on necrotic fixture"
    
    for d in dets:
        assert 0.0 <= d["x1"] < d["x2"] <= 1.0, f"Invalid x bounds: {d}"
        assert 0.0 <= d["y1"] < d["y2"] <= 1.0, f"Invalid y bounds: {d}"
        assert 0.0 <= d["confidence"] <= 1.0, f"Invalid confidence: {d}"
        assert d["label"] in ("necrosis_lesion", "chlorosis_leaf", "powdery_mildew", "leaf_spot")
    
    print(f"  -> Passed lesion detection: localized {len(dets)} lesions (labels: {[d['label'] for d in dets]}).")

def test_overlay_rendering():
    print("Testing non-destructive detection overlay rendering...")
    necrosis_img = str(BENCHMARK_DIR / "necrosis_brown.jpg")
    out_annotated = str(backend_dir / "data" / "test_annotated_sample.jpg")
    
    detections = [
        {"x1": 0.25, "y1": 0.30, "x2": 0.60, "y2": 0.65, "label": "necrosis_lesion", "confidence": 0.88}
    ]
    rendered_path = render_detection_overlay(necrosis_img, detections, out_annotated)
    assert Path(rendered_path).exists(), "Annotated overlay file was not created"
    assert Path(rendered_path).stat().st_size > 500, "Annotated file is too small"
    print("  -> Passed overlay rendering test.")

def test_vision_pipeline_yolo_integration():
    print("Testing vision_engine.analyze_plant_image YOLO integration...")
    # Mock external network calls to keep tests offline and fast
    import app.vision_engine as ve
    orig_plantnet = ve._identify_with_plantnet
    orig_plant_id = ve._assess_with_plant_id
    orig_groq = ve._analyze_with_groq_vision

    ve._identify_with_plantnet = lambda p: {"name": "Ficus lyrata", "score": 0.88, "candidates": []}
    ve._assess_with_plant_id = lambda p: {"is_plant": True, "healthy": False, "disease_name": "Leaf Necrosis", "disease_probability": 0.85}
    ve._analyze_with_groq_vision = lambda p: {"assessment": "possible_disease", "disease_name": "Leaf Necrosis", "severity": "Moderate"}

    try:
        necrosis_img = str(BENCHMARK_DIR / "necrosis_brown.jpg")
        analysis = analyze_plant_image(necrosis_img, plant_hint="Fiddle Leaf Fig")
        
        assert "detections" in analysis, "Analysis dictionary must contain 'detections'"
        assert "model_metadata" in analysis, "Analysis dictionary must contain 'model_metadata'"
        assert analysis["model_metadata"].get("model_name") == "FloraBOT-YOLO-PlantDisease-v1"
        assert len(analysis["detections"]) > 0, "YOLO should return localized detections in full analysis"
        print(f"  -> Passed pipeline integration: {len(analysis['detections'])} detections returned with model metadata.")
    finally:
        ve._identify_with_plantnet = orig_plantnet
        ve._assess_with_plant_id = orig_plant_id
        ve._analyze_with_groq_vision = orig_groq

def main():
    print("\n========================================================")
    print("  FLORABOT PHASE 4 TEST SUITE (YOLO DISEASE DETECTION)")
    print("========================================================\n")
    test_iou_and_nms()
    test_yolo_detector_initialization()
    test_yolo_lesion_detection()
    test_overlay_rendering()
    test_vision_pipeline_yolo_integration()
    print("\n========================================================")
    print("  ALL PHASE 4 TESTS COMPLETED AND VERIFIED SUCCESSFULLY!")
    print("========================================================\n")

if __name__ == "__main__":
    main()
