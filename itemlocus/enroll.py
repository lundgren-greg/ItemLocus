"""Enroll an item by name, with 0 or more reference photos.

Only embeddings are stored. Reference images are never written, and person
regions are blacked out before they are cropped or embedded.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .geometry import drop_person_overlaps
from .ingest import clean_label, load_image, sanitize
from .interfaces import Detector, Embedder, is_person
from .store import Store

MAX_REFS = 10


@dataclass
class EnrollResult:
    name: str
    query: str
    refs_added: int = 0
    whole_photo: int = 0  # references where no box was found, so the whole photo was used
    notes: list = field(default_factory=list)


def enroll(name, refs, store: Store, detector: Detector, embedder: Embedder, query=None) -> EnrollResult:
    name = clean_label(name, "item name")
    query = clean_label(query, "query") if query else name
    refs = list(refs)
    if len(refs) > MAX_REFS:
        raise ValueError(f"at most {MAX_REFS} reference photos")
    crops, res = [], EnrollResult(name, query)
    for ref in refs:
        img, persons = sanitize(load_image(ref), detector)
        dets = [d for d in detector.detect(img, [query]) if not is_person(d.label)]
        dets = drop_person_overlaps(dets, persons)
        if dets:
            b = max(dets, key=lambda d: d.score).box
            crops.append(img.crop(tuple(int(v) for v in b)))
        else:
            crops.append(img)
            res.whole_photo += 1
    vecs = embedder.embed(crops) if crops else None
    store.add_item(name, query, vecs, embedder.name)
    res.refs_added = len(crops)
    if res.whole_photo:
        res.notes.append(f"{res.whole_photo} reference photo(s) had no detected '{query}'; used the whole photo")
    return res
