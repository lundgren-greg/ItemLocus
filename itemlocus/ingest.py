"""Photo ingest: strip metadata, mask people, store a clean indexed copy.

Privacy rule: person and face pixels are painted black before anything is
written. Only the person box geometry is kept (so later matches that overlap
a person can be dropped). Metadata (EXIF, GPS, ICC) is never copied because
the stored file is a fresh JPEG encoded from raw pixels.
"""
from __future__ import annotations

import hashlib
import io
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError

from .config import Config
from .geometry import pad
from .interfaces import PERSON_QUERIES, Detector, is_person
from .store import PhotoRecord, Store

IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".bmp"})
MAX_SIDE = 2048
PERSON_MIN_SCORE = 0.15  # low on purpose: a false mask costs little, a miss costs more
MASK_PAD = 0.1


def clean_label(value: str, what: str, maxlen: int = 80) -> str:
    value = (value or "").strip()
    if not value or len(value) > maxlen or any(ord(c) < 32 for c in value):
        raise ValueError(f"invalid {what}: must be 1-{maxlen} printable characters")
    return value


def safe_filename(name: str) -> str:
    """Reject (not repair) names that could escape a folder or are not images."""
    bad = (not name or name != name.strip() or "\x00" in name or ".." in name
           or any(c in name for c in "/\\:"))
    if bad or Path(name).suffix.lower() not in IMAGE_EXTS:
        raise ValueError("unsafe or unsupported file name")
    return name


def load_image(source) -> Image.Image:
    """Open a path or bytes as upright RGB pixels with no metadata attached."""
    with Image.open(io.BytesIO(source) if isinstance(source, (bytes, bytearray)) else source) as im:
        img = ImageOps.exif_transpose(im).convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    return img


def sanitize(img: Image.Image, detector: Detector):
    """Paint person/face regions black in place; return (image, person boxes)."""
    w, h = img.size
    dets = detector.detect(img, PERSON_QUERIES)
    persons = [pad(d.box, MASK_PAD, w, h) for d in dets if is_person(d.label) and d.score >= PERSON_MIN_SCORE]
    draw = ImageDraw.Draw(img)
    for box in persons:
        draw.rectangle(box, fill=(0, 0, 0))
    return img, persons


def ingest_image(img: Image.Image, room, store: Store, cfg: Config, detector: Detector) -> PhotoRecord:
    img, persons = sanitize(img, detector)
    photo_id = hashlib.sha256(img.tobytes() + repr(img.size).encode()).hexdigest()[:16]
    cfg.ensure()
    img.save(cfg.indexed_dir / f"{photo_id}.jpg", "JPEG", quality=90)  # no exif= argument: none is written
    rec = PhotoRecord(photo_id, room, img.width, img.height, [list(b) for b in persons], time.time())
    store.add_photo(rec)
    return rec


def ingest_upload(data: bytes, filename: str, room, store: Store, cfg: Config, detector: Detector) -> PhotoRecord:
    """Entry point for uploaded bytes: the client file name is validated, never used as a path."""
    safe_filename(filename)
    return ingest_image(load_image(data), room, store, cfg, detector)


def collect_images(paths) -> list[tuple[Path, str | None]]:
    """Expand files and folders. A sub-folder name becomes the room label."""
    found = []
    for p in map(Path, paths):
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.suffix.lower() in IMAGE_EXTS and f.is_file():
                    rel = f.relative_to(p)
                    found.append((f, rel.parts[0] if len(rel.parts) > 1 else None))
        elif p.is_file():
            found.append((p, None))
        else:
            raise FileNotFoundError(f"not found: {p.name}")
    return found


def ingest_paths(paths, room, store: Store, cfg: Config, detector: Detector):
    """Returns (records, skipped file names)."""
    records, skipped = [], []
    if room is not None:
        room = clean_label(room, "room", 60)
    for f, folder_room in collect_images(paths):
        try:
            img = load_image(f)
        except (UnidentifiedImageError, OSError):
            skipped.append(f.name)
            continue
        records.append(ingest_image(img, room or folder_room, store, cfg, detector))
    return records, skipped
