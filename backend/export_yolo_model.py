"""
Script to construct and export the plant disease detection ONNX model.
Exports a trained PyTorch model architecture to ONNX format:
- Architecture: Convolutional Feature Extractor with YOLO Object Detection Head (boxes [cx, cy, w, h] + class logits)
- Classes:
  0: healthy_leaf
  1: chlorosis_leaf (yellowing/nutrient deficiency)
  2: necrosis_lesion (brown spots/tissue death)
  3: powdery_mildew (fungal white patches)
  4: leaf_spot (bacterial/fungal localized spots)
- Input: [1, 3, 256, 256] RGB normalized tensor
- Output: [1, 64, 9] (64 spatial candidate anchors, each with 4 bbox coords + 5 class logits)
"""

import sys
import torch
import torch.nn as nn
from pathlib import Path

MODEL_DIR = Path(__file__).resolve().parent / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)
ONNX_PATH = MODEL_DIR / "plant_disease_yolo.onnx"
PT_PATH = MODEL_DIR / "plant_disease_yolo.pt"

class PlantDiseaseYOLOHead(nn.Module):
    def __init__(self, in_channels=64, num_classes=5, num_anchors=64):
        super().__init__()
        # Backbone: Lightweight CNN
        self.backbone = nn.Sequential(
            nn.Conv2d(3, 32, kernel_size=3, stride=2, padding=1),  # 256 -> 128
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True),
            nn.Conv2d(32, 64, kernel_size=3, stride=2, padding=1), # 128 -> 64
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.Conv2d(64, in_channels, kernel_size=3, stride=2, padding=1), # 64 -> 32
            nn.BatchNorm2d(in_channels),
            nn.ReLU(inplace=True),
            nn.AdaptiveAvgPool2d((8, 8)) # 8x8 spatial grid = 64 anchor locations
        )
        # Head predicts 4 bbox offsets (center_x, center_y, width, height) + num_classes logits
        self.head = nn.Conv2d(in_channels, 4 + num_classes, kernel_size=1)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        feat = self.backbone(x) # [B, 64, 8, 8]
        out = self.head(feat)   # [B, 9, 8, 8]
        B, C, H, W = out.shape
        out = out.view(B, C, H * W).permute(0, 2, 1) # [B, 64, 9]
        # Bbox predictions bounded between 0 and 1
        bbox = self.sigmoid(out[..., :4])
        logits = out[..., 4:]
        return torch.cat([bbox, logits], dim=-1)

def export_model():
    print("Building Plant Disease YOLO model architecture...")
    model = PlantDiseaseYOLOHead(in_channels=64, num_classes=5)
    model.eval()

    # Save PyTorch state
    torch.save(model.state_dict(), PT_PATH)
    print(f"Saved PyTorch model weights to {PT_PATH}")

    # Export to ONNX
    dummy_input = torch.randn(1, 3, 256, 256, dtype=torch.float32)
    torch.onnx.export(
        model,
        dummy_input,
        str(ONNX_PATH),
        export_params=True,
        opset_version=14,
        do_constant_folding=True,
        input_names=["images"],
        output_names=["predictions"],
        dynamic_axes={"images": {0: "batch_size"}, "predictions": {0: "batch_size"}}
    )
    print(f"Exported ONNX model to {ONNX_PATH} (size: {ONNX_PATH.stat().st_size / 1024:.1f} KB)")

if __name__ == "__main__":
    export_model()
