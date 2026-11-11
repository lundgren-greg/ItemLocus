"""Box maths: overlap, non-max suppression, person filtering."""
from __future__ import annotations

from typing import Iterable, Sequence

from .interfaces import Box, Detection


def area(b: Box) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def intersection(a: Box, b: Box) -> float:
    return area((max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])))


def iou(a: Box, b: Box) -> float:
    inter = intersection(a, b)
    union = area(a) + area(b) - inter
    return inter / union if union > 0 else 0.0


def overlap_fraction(box: Box, other: Box) -> float:
    """Share of `box` that lies inside `other`."""
    a = area(box)
    return intersection(box, other) / a if a > 0 else 0.0


def clip(b: Box, width: int, height: int) -> Box:
    return (max(0.0, b[0]), max(0.0, b[1]), min(float(width), b[2]), min(float(height), b[3]))


def pad(b: Box, frac: float, width: int, height: int) -> Box:
    dx, dy = (b[2] - b[0]) * frac, (b[3] - b[1]) * frac
    return clip((b[0] - dx, b[1] - dy, b[2] + dx, b[3] + dy), width, height)


def nms(dets: Sequence[Detection], iou_threshold: float = 0.5) -> list[Detection]:
    kept: list[Detection] = []
    for d in sorted(dets, key=lambda d: d.score, reverse=True):
        if all(iou(d.box, k.box) < iou_threshold for k in kept):
            kept.append(d)
    return kept


def drop_person_overlaps(
    dets: Iterable[Detection], persons: Sequence[Box], threshold: float = 0.5
) -> list[Detection]:
    """Drop candidates whose area mostly lies inside a person box."""
    return [d for d in dets if all(overlap_fraction(d.box, p) < threshold for p in persons)]
