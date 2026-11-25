"""
FloraBOT Vision Engine Baseline Benchmark Evaluator
Iterates through benchmark dataset fixtures, evaluates algorithmic quality gating
and disease detection against ground truth, and outputs:
- Confusion Matrix: True Positive (TP), False Positive (FP), True Negative (TN), False Negative (FN)
- Precision, Recall, F1 Score, Accuracy
- Quality Gate screening accuracy & rejection rate
- Produces vision_evaluation_report.json
"""

import sys
import json
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.vision_engine import assess_image_quality, analyze_leaf_computer_vision

def run_vision_benchmark():
    benchmark_dir = backend_dir / "data" / "benchmark_dataset"
    manifest_path = benchmark_dir / "ground_truth.json"

    if not manifest_path.exists():
        print(f"Error: Manifest not found at {manifest_path}")
        # Auto generate if missing
        from data.generate_benchmark_fixtures import generate_fixtures
        generate_fixtures()

    with open(manifest_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    print(f"==================================================")
    print(f"  FLORABOT VISION ENGINE BENCHMARK EVALUATOR")
    print(f"  Dataset: {benchmark_dir} ({len(cases)} items)")
    print(f"==================================================")

    # Metrics counters for Disease Detection on analyzable images
    # TP: Ground truth = diseased (yes) AND engine = diseased (yes)
    # FP: Ground truth = healthy (no) AND engine = diseased (yes)
    # TN: Ground truth = healthy (no) AND engine = healthy (no)
    # FN: Ground truth = diseased (yes) AND engine = healthy (no)
    tp = 0
    fp = 0
    tn = 0
    fn = 0

    # Quality Gate counters
    correct_quality_classifications = 0
    quality_rejections = 0
    total_samples = len(cases)

    results_detail = []

    for item in cases:
        img_name = item["filename"]
        img_path = benchmark_dir / img_name
        expected_quality = item["expected_quality"]
        expected_disease = item["expected_disease_detected"]

        # Run quality assessment
        quality = assess_image_quality(str(img_path))
        is_suitable = quality["is_suitable"]

        if not is_suitable:
            predicted_quality = "rejected"
            predicted_disease = "uncertain"
            quality_rejections += 1
            cv_res = None
        else:
            # Run local CV
            cv_res = analyze_leaf_computer_vision(str(img_path))
            if not cv_res.get("is_suitable"):
                predicted_quality = "rejected"
                predicted_disease = "uncertain"
                quality_rejections += 1
            else:
                predicted_quality = "suitable"
                predicted_disease = cv_res.get("disease_detected", "uncertain")

        # Evaluate Quality Gate
        quality_correct = (predicted_quality == expected_quality)
        if quality_correct:
            correct_quality_classifications += 1

        # Evaluate Disease Classification (for suitable images)
        if expected_quality == "suitable":
            if expected_disease == "yes":
                if predicted_disease == "yes":
                    tp += 1
                else:
                    fn += 1
            elif expected_disease == "no":
                if predicted_disease == "yes":
                    fp += 1
                else:
                    tn += 1

        status_marker = "PASS" if quality_correct and (expected_quality == "rejected" or predicted_disease == expected_disease) else "FAIL"
        print(f"[{status_marker}] {img_name:<26} Quality: {predicted_quality:<8} (exp: {expected_quality:<8}) | Disease: {predicted_disease:<8} (exp: {expected_disease:<8})")

        results_detail.append({
            "filename": img_name,
            "description": item.get("description", ""),
            "expected_quality": expected_quality,
            "predicted_quality": predicted_quality,
            "quality_correct": quality_correct,
            "expected_disease": expected_disease,
            "predicted_disease": predicted_disease,
            "quality_metrics": {
                "blur_score": quality.get("blur_score"),
                "mean_brightness": quality.get("mean_brightness"),
                "contrast_std": quality.get("contrast_std"),
                "rejection_reason": quality.get("rejection_reason")
            }
        })

    # Calculations
    quality_accuracy = correct_quality_classifications / total_samples if total_samples > 0 else 0.0
    
    analyzable_samples = tp + fp + tn + fn
    accuracy = (tp + tn) / analyzable_samples if analyzable_samples > 0 else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    print(f"\n--- Benchmark Summary Metrics ---")
    print(f"Total Test Fixtures Evaluated: {total_samples}")
    print(f"Quality Gate Classification Accuracy: {quality_accuracy:.1%} ({correct_quality_classifications}/{total_samples})")
    print(f"Quality Rejection Rate: {quality_rejections / total_samples:.1%} ({quality_rejections}/{total_samples})")
    print(f"Confusion Matrix (Analyzable Leaves): TP={tp}, FP={fp}, TN={tn}, FN={fn}")
    print(f"Accuracy:  {accuracy:.1%}")
    print(f"Precision: {precision:.1%}")
    print(f"Recall:    {recall:.1%}")
    print(f"F1 Score:  {f1:.3f}")

    report = {
        "dataset_size": total_samples,
        "quality_gate": {
            "accuracy": round(quality_accuracy, 4),
            "rejections": quality_rejections,
            "rejection_rate": round(quality_rejections / total_samples, 4)
        },
        "confusion_matrix": {
            "tp": tp,
            "fp": fp,
            "tn": tn,
            "fn": fn
        },
        "performance": {
            "accuracy": round(accuracy, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1, 4)
        },
        "details": results_detail
    }

    report_path = backend_dir / "data" / "vision_evaluation_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"\nReport written to: {report_path}")
    return report

if __name__ == "__main__":
    report = run_vision_benchmark()
    # Check assertions for passing criteria
    assert report["quality_gate"]["accuracy"] >= 0.85, f"Quality accuracy {report['quality_gate']['accuracy']} below 85%"
    assert report["performance"]["accuracy"] >= 0.85, f"Performance accuracy {report['performance']['accuracy']} below 85%"
    print("ALL BENCHMARK ASSERTIONS PASSED!")
