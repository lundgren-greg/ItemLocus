"""Ingest, enroll and find end to end with fake models and synthetic images."""
import numpy as np
import pytest
from PIL import Image

from conftest import BLUE, GREEN, RED, FakeDetector, scene
from itemlocus.enroll import enroll
from itemlocus.ingest import ingest_image, ingest_paths
from itemlocus.interfaces import Detection, is_person
from itemlocus.query import find

KEYS_A = (100, 100, 140, 130)
KEYS_B = (200, 60, 240, 90)


def add(env, img, room=None):
    return ingest_image(img, room, env.store, env.cfg, env.det)


def ask(env, q="keys", **kw):
    return find(q, env.store, env.cfg, env.det, env.emb, **kw)


def test_exif_and_gps_stripped(env):
    exif = Image.Exif()
    exif[0x010F] = "TestCam"
    exif[0x8825] = {1: "N", 2: (45.0, 30.0, 0.0), 3: "W", 4: (122.0, 40.0, 0.0)}  # GPS IFD
    src = env.tmp / "src.jpg"
    scene((RED, KEYS_A)).save(src, exif=exif)
    with Image.open(src) as im:  # the test input really carries GPS
        assert im.getexif().get_ifd(0x8825)
    rec = ingest_paths([src], "hall", env.store, env.cfg, env.det)[0][0]
    stored = env.cfg.indexed_dir / f"{rec.id}.jpg"
    with Image.open(stored) as im:
        assert not im.getexif() and "exif" not in im.info and not im.getexif().get_ifd(0x8825)
    raw = stored.read_bytes()
    assert b"Exif" not in raw and b"TestCam" not in raw


def test_person_pixels_blacked_and_geometry_kept(env):
    rec = add(env, scene((GREEN, (10, 10, 90, 120)), (RED, KEYS_A)))
    assert rec.masks  # person and face queries may both fire
    with Image.open(env.cfg.indexed_dir / f"{rec.id}.jpg") as im:
        arr = np.asarray(im.convert("RGB")).astype(int)
    assert arr[20:110, 20:80].max() < 20  # person region is black; no green survives
    assert (np.abs(arr - GREEN).sum(axis=2) < 90).sum() == 0
    assert arr[110, 120].tolist()[0] > 150  # keys outside the person are intact


def test_item_overlapping_person_is_skipped(env):
    class Scripted(FakeDetector):
        def detect(self, image, queries):
            if any(is_person(q) for q in queries) and len(queries) == 2 and self.phase == "ingest":
                return [Detection("person", (40, 40, 160, 160), 0.9)]
            return [Detection("keys", self.keys, 0.5)]

    det = Scripted()
    det.phase, det.keys = "ingest", (60, 60, 100, 100)
    ingest_image(scene(), None, env.store, env.cfg, det)
    det.phase = "find"
    enroll("keys", [], env.store, det, env.emb)
    ans = find("keys", env.store, env.cfg, det, env.emb)
    assert (ans.status, ans.reason) == ("not_sure", "no_candidates")  # candidate sits inside the person box
    det.keys = (200, 150, 240, 190)
    assert find("keys", env.store, env.cfg, det, env.emb).status == "found"


def test_enroll_zero_one_three_refs(env):
    r0 = enroll("wallet", [], env.store, env.det, env.emb)
    assert r0.refs_added == 0 and env.store.get_item("wallet").refs.shape[0] == 0
    ref = scene((RED, KEYS_A))
    assert enroll("house keys", [ref], env.store, env.det, env.emb, query="keys").refs_added == 1
    r3 = enroll("shed keys", [ref, scene((RED, KEYS_B)), scene()], env.store, env.det, env.emb, query="keys")
    assert (r3.refs_added, r3.whole_photo) == (3, 1) and env.store.get_item("shed keys").refs.shape[0] == 3
    with pytest.raises(ValueError):
        enroll("x", [ref] * 11, env.store, env.det, env.emb)
    assert list(env.cfg.indexed_dir.iterdir()) == []  # reference photos are never stored


def test_enroll_masks_person_in_reference(env):
    seen = []

    class Spy(type(env.emb)):
        def embed(self, images):
            seen.extend(np.asarray(i.convert("RGB")) for i in images)
            return super().embed(images)

    enroll("keys", [scene((GREEN, (10, 10, 90, 120)), (RED, KEYS_A))], env.store, env.det, Spy(), query="keys")
    assert all((np.abs(a.astype(int) - GREEN).sum(axis=2) < 90).sum() == 0 for a in seen)


def test_find_picks_matching_room_with_references(env):
    add(env, scene((RED, KEYS_A), (BLUE, KEYS_B)), "kitchen")
    add(env, scene((BLUE, KEYS_A)), "office")
    enroll("front keys", [scene((RED, KEYS_B))], env.store, env.det, env.emb, query="keys")
    enroll("shed keys", [scene((BLUE, KEYS_A))], env.store, env.det, env.emb, query="keys")
    a = ask(env, "Where are my front keys?")
    assert (a.status, a.room) == ("found", "kitchen") and a.confidence > 0.9
    assert a.box == pytest.approx(KEYS_A, abs=3) and (env.cfg.crops_dir / a.crop).is_file()
    assert env.store.get_last_seen("front keys")["room"] == "kitchen"
    assert Image.open(env.cfg.crops_dir / a.crop).size == pytest.approx((40, 30), abs=3)


def test_two_similar_items_text_only_is_not_sure(env):
    add(env, scene((RED, KEYS_A), (BLUE, KEYS_B)), "kitchen")
    enroll("front keys", [], env.store, env.det, env.emb, query="keys")
    a = ask(env, "front keys")
    assert (a.status, a.reason) == ("not_sure", "ambiguous")
    assert a.room is None and a.crop is None and "kitchen" not in a.message  # no guessed room


def test_below_threshold_is_not_sure(env):
    add(env, scene((BLUE, KEYS_A)), "office")
    enroll("front keys", [scene((RED, KEYS_B))], env.store, env.det, env.emb, query="keys")
    a = ask(env, "front keys")
    assert (a.status, a.reason) == ("not_sure", "below_threshold") and a.room is None
    assert ask(env, "front keys", threshold=0.0, margin=0.0).status == "found"  # threshold is what blocked it
    assert a.candidates and a.candidates[0]["confidence"] < 0.6


def test_absent_item_is_not_sure(env):
    add(env, scene(), "hall")
    enroll("keys", [], env.store, env.det, env.emb)
    assert ask(env).reason == "no_candidates"


def test_same_item_in_two_photos_is_ambiguous(env):
    add(env, scene((RED, KEYS_A)), "kitchen")
    add(env, scene((RED, KEYS_B)), "office")
    enroll("keys", [], env.store, env.det, env.emb)
    assert ask(env).reason == "ambiguous"


def test_unknown_item_and_empty_store(env):
    a = ask(env, "Where is my passport?")
    assert a.status == "unknown_item" and "passport" in a.item
    enroll("keys", [], env.store, env.det, env.emb)
    assert ask(env).reason == "no_candidates"  # enrolled but no photos


def test_ingest_folder_uses_subfolder_as_room(env):
    d = env.tmp / "shots"
    (d / "kitchen").mkdir(parents=True)
    scene((RED, KEYS_A)).save(d / "kitchen" / "a.png")
    scene((BLUE, KEYS_B)).save(d / "b.png")
    (d / "notes.txt").write_text("not an image")
    recs, skipped = ingest_paths([d], None, env.store, env.cfg, env.det)
    assert sorted(str(r.room) for r in recs) == ["None", "kitchen"] and skipped == []
    recs, _ = ingest_paths([d / "b.png"], "Hall", env.store, env.cfg, env.det)
    assert recs[0].room == "Hall"
