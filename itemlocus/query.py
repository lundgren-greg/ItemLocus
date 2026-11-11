"""Answer "where are my keys?" from the indexed photos."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from . import ranking
from .config import Config
from .geometry import area, drop_person_overlaps, nms
from .interfaces import PERSON_QUERIES, Detector, Embedder, is_person
from .ranking import Scored
from .store import Store

_QUESTION = re.compile(
    r"^\s*(?:where(?:'s| is| are| did i (?:put|leave))?)\s+(?:my|the|our)?\s*(.+?)\s*[?.!]*\s*$", re.I
)
MAX_CANDIDATES_PER_PHOTO = 5


def extract_item(text: str) -> str:
    """'Where are my keys?' -> 'keys'. Anything else is returned stripped."""
    m = _QUESTION.match(text)
    return (m.group(1) if m else text).strip()


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "item"


@dataclass
class Answer:
    item: str
    status: str  # "found", "not_sure", "unknown_item"
    reason: str = ""
    confidence: float = 0.0
    photo_id: str | None = None
    room: str | None = None
    box: tuple | None = None
    crop: str | None = None  # file name inside the crops folder
    image_size: tuple | None = None
    message: str = ""
    candidates: list = field(default_factory=list)  # for calibration; never shown as an answer

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _text_answer(item: str, d: ranking.Decision) -> str:
    if d.status == "found":
        b = d.best
        where = f"in the {b.room}" if b.room else "in a photo with no room label"
        return f"Found: {item} {where} (confidence {b.confidence:.0%}, photo {b.photo_id[:8]})."
    why = {
        "no_candidates": "I could not find anything that looks like it in the photos.",
        "below_threshold": "The best match was too weak to trust.",
        "ambiguous": "Two places matched about equally well.",
    }[d.reason]
    return f"I'm not sure where {item} is. {why}"


def find(question: str, store: Store, cfg: Config, detector: Detector, embedder: Embedder,
         threshold: float = ranking.DEFAULT_THRESHOLD, margin: float = ranking.DEFAULT_MARGIN) -> Answer:
    item = store.get_item(question.strip()) or store.get_item(extract_item(question))
    if item is None:
        known = ", ".join(store.list_items()) or "none"
        return Answer(extract_item(question), "unknown_item", "unknown_item",
                      message=f"No item with that name is enrolled. Enrolled items: {known}.")
    use_refs = len(item.refs) > 0
    if use_refs and item.models != {embedder.name}:
        raise ValueError(f"'{item.name}' was enrolled with a different embedder; re-enroll it")

    # Gather candidates from every indexed photo.
    pending = []  # (record, image, detection)
    for rec in store.list_photos():
        path = cfg.indexed_dir / f"{rec.id}.jpg"
        if not path.is_file():
            continue
        with Image.open(path) as im:
            img = im.convert("RGB")
        dets = detector.detect(img, [item.query, *PERSON_QUERIES])
        persons = [tuple(m) for m in rec.masks] + [d.box for d in dets if is_person(d.label)]
        cands = [d for d in dets if not is_person(d.label) and d.score >= ranking.MIN_DET and area(d.box) >= 16]
        cands = drop_person_overlaps(nms(cands), persons)[:MAX_CANDIDATES_PER_PHOTO]
        pending += [(rec, img, d) for d in cands]

    sims = [None] * len(pending)
    if use_refs and pending:
        crops = [img.crop(tuple(int(v) for v in d.box)) for _, img, d in pending]
        sims = list((embedder.embed(crops) @ item.refs.T).max(axis=1))
    scored = [Scored(rec.id, rec.room, tuple(d.box), d.score, None if s is None else float(s),
                     ranking.confidence(d.score, None if s is None else float(s), embedder.sim_lo, embedder.sim_hi))
              for (rec, _, d), s in zip(pending, sims)]

    decision = ranking.decide(scored, threshold, margin)
    ans = Answer(item.name, decision.status, decision.reason, message=_text_answer(item.name, decision),
                 candidates=[dict(s.__dict__, box=list(s.box)) for s in decision.ranked[:5]])
    if decision.status == "found":
        b = decision.best
        img = next(im for r, im, d in pending if r.id == b.photo_id and tuple(d.box) == b.box)
        ans.crop = f"{slug(item.name)}.jpg"
        cfg.ensure()
        img.crop(tuple(int(v) for v in b.box)).save(cfg.crops_dir / ans.crop, "JPEG", quality=90)
        ans.confidence, ans.photo_id, ans.room, ans.box = b.confidence, b.photo_id, b.room, b.box
        ans.image_size = img.size
        store.set_last_seen(item.name, b.photo_id, b.room, b.box, b.confidence, ans.crop)
    return ans
