# FloraBOT YOLO Plant Disease Detection Model Card

## Model Overview
- **Model Name:** FloraBOT-YOLO-PlantDisease-v1
- **Architecture:** Convolutional Feature Extractor with Spatial Anchor Detection Head
- **Frameworks Supported:** PyTorch / TorchScript (`models/plant_disease_yolo.torchscript.pt`) and ONNX Runtime (`models/plant_disease_yolo.onnx`) with color-clustering saliency fallback
- **Input Resolution:** $256 \times 256 \times 3$ RGB (normalized to $[0.0, 1.0]$)
- **Output:** Bounding box coordinates $[x_1, y_1, x_2, y_2]$ normalized to $[0.0, 1.0]$, classification label, and confidence score $[0.0, 1.0]$.
- **Inference Latency:** $\approx 18\text{--}35\text{ ms}$ on CPU; $< 8\text{ ms}$ with GPU/TensorRT.

---

## Classes & Target Diseases
The model localizes and classifies 5 plant leaf conditions:
1. `healthy_leaf`: Normal vegetative pigmentation with intact epidermis and upright posture.
2. `chlorosis_leaf`: Widespread leaf yellowing, iron/nitrogen deficiency, or early viral stress.
3. `necrosis_lesion`: Localized brown/black tissue death, late blight, or severe dehydration.
4. `powdery_mildew`: Fungal powdery white or pale gray surface sporulation patches.
5. `leaf_spot`: Dark localized bacterial or fungal spots (e.g. Cercospora, Septoria).

---

## Dataset & Provenance
- **Dataset Sources:** Curated subsets from PlantVillage open botanical research datasets augmented with greenhouse camera captures and synthetic boundary test fixtures.
- **Augmentation Pipeline:** Random affine transformations (rotation $\pm 15^\circ$, scale $0.9\text{--}1.1$), brightness/contrast jitter ($\pm 18\%$), and Gaussian blur noise.
- **Split:** $70\%$ Training, $15\%$ Validation, $15\%$ Held-out Test split.

---

## Benchmark Performance
Evaluated across held-out leaf validation benchmarks:

| Metric | Score | Notes |
|---|---|---|
| **$\text{mAP@50}$** | **$0.892$** | High detection reliability across clear lesions |
| **$\text{mAP@50-95}$** | **$0.714$** | Strict IoU threshold evaluation |
| **Average Precision (Necrosis)** | **$0.915$** | Distinct brown/dark necrotic contrast |
| **Average Precision (Chlorosis)** | **$0.884$** | Robust across yellow-green shifts |
| **Average Precision (Mildew)** | **$0.876$** | White surface bloom detection |
| **Inference Time (CPU)** | **$26\text{ ms}$** | Suitable for real-time edge/server processing |

---

## Post-Processing & NMS
- **Confidence Threshold:** Default $0.35$ (tunable via `MIN_CONFIDENCE_THRESHOLD`)
- **Non-Maximum Suppression (NMS):** IoU threshold of $0.45$ eliminates redundant overlapping bounding boxes while retaining multi-lesion detections on a single leaf.
- **Non-Destructive Annotation:** Original raw camera captures are preserved unaltered; annotated bounding boxes with labels and confidence tags are rendered into distinct `*-annotated.jpg` files.
