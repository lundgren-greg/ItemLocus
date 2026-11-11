"""Fakes and synthetic images. No torch, no weights, no real photos."""
import types

import numpy as np
import pytest
from PIL import Image, ImageDraw

from itemlocus.config import Config
from itemlocus.interfaces import Detection, is_person
from itemlocus.store import Store

RED, BLUE, GREEN = (200, 30, 30), (30, 30, 200), (0, 200, 0)  # green block = "person"
COLORS = {"red": RED, "blue": BLUE}


def bbox_of(img, color, tol=90):
    arr = np.asarray(img.convert("RGB")).astype(int)
    ys, xs = np.nonzero(np.abs(arr - color).sum(axis=2) < tol)
    if len(xs) < 20:
        return None
    return (float(xs.min()), float(ys.min()), float(xs.max() + 1), float(ys.max() + 1))


def scene(*blocks, size=(320, 240)):
    """Grey room with coloured rectangles: scene((RED, (x0, y0, x1, y1)), ...)."""
    img = Image.new("RGB", size, (128, 128, 128))
    d = ImageDraw.Draw(img)
    for color, box in blocks:
        d.rectangle(box, fill=color)
    return img


class FakeDetector:
    """'keys' = every red/blue block; person queries = the green block."""

    def detect(self, image, queries):
        out = []
        for q in queries:
            if is_person(q):
                box = bbox_of(image, GREEN)
                out += [Detection(q, box, 0.9)] if box else []
            elif q == "keys":
                out += [Detection(q, b, 0.5) for c in COLORS.values() if (b := bbox_of(image, c))]
        return out


class FakeEmbedder:
    name, sim_lo, sim_hi = "fake", 0.5, 0.95

    def embed(self, images):
        v = np.array([np.asarray(i.convert("RGB")).reshape(-1, 3).mean(axis=0) for i in images], dtype=np.float32)
        return v / np.linalg.norm(v, axis=1, keepdims=True)


@pytest.fixture
def env(tmp_path):
    cfg = Config(tmp_path / "photos", tmp_path / "data")
    cfg.ensure()
    store = Store(cfg.db_path)
    yield types.SimpleNamespace(cfg=cfg, store=store, det=FakeDetector(), emb=FakeEmbedder(), tmp=tmp_path)
    store.close()
