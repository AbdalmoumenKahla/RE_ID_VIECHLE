from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


class VehicleEmbedder:
    """Local feature extractor with a deep OSNet/ResNet primary path.

    Supply a vehicle-trained OSNet checkpoint in Settings for production. The
    deterministic colour/shape descriptor is only a diagnostic fallback when
    the optional PyTorch dependencies are missing.
    """

    def __init__(self, device: str = "auto", model_path: str = "") -> None:
        self.device_preference = device
        self.model_path = model_path
        self.kind = "initializing"
        self.device_label = "CPU"
        self.error: str | None = None
        self._torch = None
        self._model = None
        self._extractor = None
        self._transform = None
        self._load()

    def _load(self) -> None:
        try:
            import torch
            import torch.nn as nn
            from torchvision.models import ResNet50_Weights, resnet50
            from torchvision.transforms import Compose, Normalize, Resize, ToTensor

            use_cuda = self.device_preference != "cpu" and torch.cuda.is_available()
            device = "cuda" if use_cuda else "cpu"
            self.device_label = f"CUDA: {torch.cuda.get_device_name(0)}" if use_cuda else "CPU"
            # A vehicle-trained OSNet checkpoint is the preferred deployment
            # model. Torchreid's extractor accepts a local checkpoint and
            # numpy crops, while keeping all inference on this PC.
            if self.model_path and Path(self.model_path).is_file():
                try:
                    from torchreid.utils import FeatureExtractor
                    self._extractor = FeatureExtractor(
                        model_name="osnet_x1_0", model_path=self.model_path, device=device,
                    )
                    self._torch = torch
                    self.kind = "local OSNet vehicle Re-ID checkpoint"
                    return
                except Exception:
                    # A non-OSNet checkpoint may still be a compatible
                    # ResNet50 state dict, handled by the fallback below.
                    self._extractor = None
            # A local, vehicle-trained checkpoint has priority. torchvision is
            # otherwise a practical baseline feature backbone, not a promise of
            # vehicle-specialized accuracy.
            weights = ResNet50_Weights.DEFAULT
            model = resnet50(weights=weights)
            if self.model_path and Path(self.model_path).is_file():
                state = torch.load(self.model_path, map_location=device)
                state = state.get("state_dict", state)
                model.load_state_dict({key.replace("module.", ""): value for key, value in state.items()}, strict=False)
                self.kind = "local checkpoint (ResNet50)"
            else:
                self.kind = "ResNet50 ImageNet baseline"
            model.fc = nn.Identity()
            self._model = model.eval().to(device)
            self._torch = torch
            self._transform = Compose([Resize((256, 256)), ToTensor(), Normalize(ResNet50_Weights.DEFAULT.transforms().mean, ResNet50_Weights.DEFAULT.transforms().std)])
        except Exception as exc:
            self.error = str(exc)
            self.kind = "CV fallback (install PyTorch for deep Re-ID)"

    def embed(self, bgr_crop: np.ndarray) -> np.ndarray:
        if bgr_crop is None or bgr_crop.size == 0:
            return np.zeros(1, dtype=np.float32)
        if self._extractor is not None:
            vector = self._extractor([bgr_crop]).detach().cpu().numpy().ravel().astype(np.float32)
            return self._normalise(vector)
        if self._model is not None and self._torch is not None:
            rgb = cv2.cvtColor(bgr_crop, cv2.COLOR_BGR2RGB)
            from PIL import Image
            tensor = self._transform(Image.fromarray(rgb)).unsqueeze(0).to(next(self._model.parameters()).device)
            with self._torch.no_grad():
                vector = self._model(tensor).detach().cpu().numpy().ravel().astype(np.float32)
            return self._normalise(vector)
        # A stable fallback supports end-to-end demos, but is visibly labelled
        # in the UI because it is not a replacement for a trained Re-ID model.
        image = cv2.resize(bgr_crop, (64, 64), interpolation=cv2.INTER_AREA)
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1, 2], None, [12, 8, 4], [0, 180, 0, 256, 0, 256]).ravel()
        edges = cv2.resize(cv2.Canny(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), 60, 160), (16, 16)).ravel().astype(np.float32) / 255
        return self._normalise(np.concatenate((hist.astype(np.float32), edges)))

    @staticmethod
    def _normalise(vector: np.ndarray) -> np.ndarray:
        norm = float(np.linalg.norm(vector))
        return vector / norm if norm else vector
