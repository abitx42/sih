# Localized Image Alteration Model Setup Guide: TruFor & Deep Localization

Truth Lens includes a built-in multi-signal CPU localization engine (`TruthLens-LocalELA-v1`) that runs without external heavy GPU checkpoints. 

This guide provides step-by-step instructions for deploying deep-learning pixel-level forgery localization architectures (such as **TruFor** or **CAT-Net**) for GPU-accelerated production environments.

---

## 1. Prerequisites & Hardware Requirements

- **GPU**: NVIDIA GPU with >= 8 GB VRAM (RTX 3080/4080/A100 or higher recommended for high-res images).
- **CUDA Toolkit**: 11.8 or 12.1+.
- **PyTorch**: `>= 2.2.0` with CUDA support.

---

## 2. TruFor Model Integration Details

TruFor (*An RGB-N Forgery Detector with Extraction of Noise Features and Anomaly Localization*) is an open-source forensic localization framework published by the GRIP team (University of Naples Federico II).

### A. Download Checkpoints
Clone or download the weights into the `storage/models/trufor/` directory:
```bash
mkdir -p storage/models/trufor
cd storage/models/trufor

# Download official pinned checkpoint weights (approx. 250 MB)
# SHA256: 7d18c991e604f323896fae8524d77519bfb8bc87ebae3d82d4da2ee18fc479c3
wget https://raw.githubusercontent.com/grip-unina/TruFor/main/weights/trufor.pth.tar -O trufor.pth.tar
```

### B. Environment Dependencies
Ensure the environment contains required scientific packages:
```bash
pip install timm scikit-image yacs
```

### C. Drop-in LocalizationAnalyzer Implementation
Create `app/analyzers/trufor_localizer.py` implementing the standard `LocalizationAnalyzer` contract:

```python
from pathlib import Path
from typing import Dict, Any, Optional
from PIL import Image
import torch
from app.analyzers.localization_analyzer import (
    LOCALIZATION_STATUS_AVAILABLE,
    LOCALIZATION_STATUS_UNAVAILABLE,
    MODEL_NAME
)

class TruForLocalizer:
    def __init__(self, weights_path: Path):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = self._load_model(weights_path)
    
    def analyze(self, file_path: Path, evidence_id: str, img: Optional[Image.Image] = None) -> Dict[str, Any]:
        # Perform RGB-N extraction, anomaly map inference, and reliability map calculation
        # Return dict conforming exactly to LocalizationResult schema
        ...
```

---

## 3. Truthful Deployment Guarantee

1. **No Mocking**: When a deep localization model is not installed or GPU assets are unavailable, Truth Lens automatically runs the CPU heuristic pipeline (`TruthLens-LocalELA-v1`) and clearly documents its limitations.
2. **Honest Limitations**: The UI and reports clearly indicate that image-only localization maps reflect statistical anomaly concentrations and do not prove legal authenticity or identify the specific tool used.
