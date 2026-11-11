"""Real model wrappers. Heavy libraries are imported lazily, inside the classes.

UNTESTED END TO END in the session that wrote this (no weights were
downloaded). First run downloads weights from the model host; nothing else
touches the network.
"""
from __future__ import annotations

from typing import Sequence

from .interfaces import Detection

DETECTORS = ("owlv2", "yoloworld")
EMBEDDERS = ("clip", "dinov2")


def pick_device(requested: str | None = None) -> str:
    if requested:
        return requested
    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


class OwlV2Detector:
    MODEL = "google/owlv2-base-patch16-ensemble"  # Apache-2.0

    def __init__(self, device: str | None = None, min_score: float = 0.05):
        import torch
        from transformers import Owlv2ForObjectDetection, Owlv2Processor

        self.torch, self.min_score = torch, min_score
        self.device = pick_device(device)
        self.processor = Owlv2Processor.from_pretrained(self.MODEL)
        self.model = Owlv2ForObjectDetection.from_pretrained(self.MODEL).to(self.device).eval()

    def detect(self, image, queries: Sequence[str]) -> list[Detection]:
        queries = list(queries)
        inputs = self.processor(text=[[f"a photo of {q}" for q in queries]], images=image, return_tensors="pt")
        inputs = inputs.to(self.device)
        with self.torch.no_grad():
            out = self.model(**inputs)
        # OWLv2 pads the image to a square, so boxes are relative to the padded side.
        side = max(image.size)
        res = self.processor.post_process_object_detection(
            outputs=out, threshold=self.min_score, target_sizes=self.torch.tensor([[side, side]])
        )[0]
        w, h = image.size
        return [
            Detection(queries[int(lbl)], (max(0.0, b[0]), max(0.0, b[1]), min(float(w), b[2]), min(float(h), b[3])), float(s))
            for s, lbl, b in zip(res["scores"].tolist(), res["labels"].tolist(), res["boxes"].tolist())
        ]


class YoloWorldDetector:
    """Optional. ultralytics is AGPL-3.0 and may fetch extra packages on first use."""

    MODEL = "yolov8s-worldv2.pt"

    def __init__(self, device: str | None = None, min_score: float = 0.05):
        from ultralytics import YOLOWorld

        self.device, self.min_score = pick_device(device), min_score
        self.model, self._classes = YOLOWorld(self.MODEL), None

    def detect(self, image, queries: Sequence[str]) -> list[Detection]:
        queries = list(queries)
        if self._classes != queries:
            self.model.set_classes(queries)
            self._classes = queries
        r = self.model.predict(image, conf=self.min_score, device=self.device, verbose=False)[0]
        return [Detection(queries[int(b.cls)], tuple(b.xyxy[0].tolist()), float(b.conf)) for b in r.boxes]


class _TorchEmbedder:
    name = ""
    sim_lo = sim_hi = 0.0

    def _features(self, inputs):
        raise NotImplementedError

    def embed(self, images: Sequence):
        import numpy as np

        inputs = self.processor(images=list(images), return_tensors="pt").to(self.device)
        with self.torch.no_grad():
            f = self._features(inputs)
        f = f / f.norm(dim=-1, keepdim=True)
        return f.cpu().numpy().astype(np.float32)


class ClipEmbedder(_TorchEmbedder):
    name, MODEL = "clip-vit-b32", "openai/clip-vit-base-patch32"  # MIT
    sim_lo, sim_hi = 0.55, 0.85  # uncalibrated guess

    def __init__(self, device: str | None = None):
        import torch
        from transformers import CLIPModel, CLIPProcessor

        self.torch, self.device = torch, pick_device(device)
        self.processor = CLIPProcessor.from_pretrained(self.MODEL)
        self.model = CLIPModel.from_pretrained(self.MODEL).to(self.device).eval()

    def _features(self, inputs):
        return self.model.get_image_features(**inputs)


class DinoV2Embedder(_TorchEmbedder):
    name, MODEL = "dinov2-small", "facebook/dinov2-small"  # Apache-2.0
    sim_lo, sim_hi = 0.25, 0.70  # uncalibrated guess

    def __init__(self, device: str | None = None):
        import torch
        from transformers import AutoImageProcessor, AutoModel

        self.torch, self.device = torch, pick_device(device)
        self.processor = AutoImageProcessor.from_pretrained(self.MODEL)
        self.model = AutoModel.from_pretrained(self.MODEL).to(self.device).eval()

    def _features(self, inputs):
        return self.model(**inputs).last_hidden_state[:, 0]


def load_detector(name: str = "owlv2", device: str | None = None):
    return {"owlv2": OwlV2Detector, "yoloworld": YoloWorldDetector}[name](device)


def load_embedder(name: str = "clip", device: str | None = None):
    return {"clip": ClipEmbedder, "dinov2": DinoV2Embedder}[name](device)
