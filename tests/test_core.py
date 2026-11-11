"""Pure logic: geometry, ranking, store, name handling."""
import numpy as np
import pytest

from itemlocus import ranking
from itemlocus.geometry import drop_person_overlaps, iou, nms, overlap_fraction
from itemlocus.ingest import safe_filename
from itemlocus.interfaces import Detection
from itemlocus.query import extract_item
from itemlocus.ranking import Scored, confidence, decide
from itemlocus.store import PhotoRecord, Store
from itemlocus.web import check_bind_host, parse_multipart


def test_geometry():
    assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1
    assert iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0
    assert overlap_fraction((0, 0, 10, 10), (0, 0, 5, 10)) == 0.5
    dets = [Detection("k", (0, 0, 10, 10), 0.4), Detection("k", (1, 1, 10, 10), 0.9), Detection("k", (50, 50, 60, 60), 0.2)]
    assert [d.score for d in nms(dets)] == [0.9, 0.2]


def test_person_overlap_dropped():
    inside, outside, partial = (Detection("k", b, 0.5) for b in
                                [(10, 10, 20, 20), (200, 200, 220, 220), (95, 0, 115, 10)])
    kept = drop_person_overlaps([inside, outside, partial], [(0, 0, 100, 100)])
    assert inside not in kept and outside in kept and partial in kept  # partial: only 25% inside


def S(conf, photo="a"):
    return Scored(photo, "kitchen", (0, 0, 5, 5), 0.5, None, conf)


def test_confidence_scale():
    assert confidence(0.5, 0.95, 0.5, 0.95) == 1.0
    assert confidence(0.5, 0.4, 0.5, 0.95) == 0.0
    assert confidence(0.15, 0.95, 0.5, 0.95) == pytest.approx(0.5 ** 0.5)
    assert confidence(0.5, None, 0.5, 0.95) == ranking.TEXT_ONLY_CAP  # text only is capped


def test_decide_rules():
    assert decide([]).reason == "no_candidates"
    assert decide([S(0.59)]).reason == "below_threshold"
    near = decide([S(0.9, "a"), S(0.85, "b")])
    assert (near.status, near.reason) == ("not_sure", "ambiguous")
    ok = decide([S(0.6, "a"), S(0.2, "b")])
    assert ok.status == "found" and ok.best.photo_id == "a"
    assert decide([S(0.3), S(0.9, "b")]).best.photo_id == "b"  # ranking sorts by confidence


def test_store_round_trip(tmp_path):
    s = Store(tmp_path / "t.db")
    s.add_photo(PhotoRecord("p1", "kitchen", 320, 240, [[1, 2, 3, 4]]))
    p = s.list_photos()[0]
    assert (p.id, p.room, p.masks) == ("p1", "kitchen", [[1, 2, 3, 4]])
    vecs = np.eye(3, dtype=np.float32)[:2]
    s.add_item("House Keys", "keys", vecs, "fake")
    it = s.get_item("house keys")  # case-insensitive
    assert it.query == "keys" and it.refs.shape == (2, 3) and it.models == {"fake"}
    assert np.allclose(it.refs, vecs)
    s.add_item("Wallet", "wallet")
    assert s.get_item("wallet").refs.shape[0] == 0
    s.set_last_seen("House Keys", "p1", "kitchen", (1, 2, 3, 4), 0.9, "keys.jpg")
    assert s.get_last_seen("house keys")["room"] == "kitchen"
    assert s.delete_item("house keys") and s.get_item("House Keys") is None
    assert s.get_last_seen("House Keys") is None
    s.close()


def test_extract_item():
    assert extract_item("Where are my keys?") == "keys"
    assert extract_item("where's the red toolbox") == "red toolbox"
    assert extract_item("keys") == "keys"


@pytest.mark.parametrize("bad", ["../x.jpg", "a/b.jpg", "a\\b.jpg", "C:x.jpg", "x.exe", "", "..jpg", "x\x00.jpg", " x.jpg"])
def test_unsafe_filenames_rejected(bad):
    with pytest.raises(ValueError):
        safe_filename(bad)


def test_safe_filename_ok():
    assert safe_filename("Kitchen 1.JPG") == "Kitchen 1.JPG"


def test_loopback_only_binding():
    for ok in ("127.0.0.1", "::1", "localhost"):
        check_bind_host(ok)
    for bad in ("0.0.0.0", "192.168.1.5", "example.com", "::"):
        with pytest.raises(ValueError, match="loopback"):
            check_bind_host(bad)
    check_bind_host("0.0.0.0", allow_non_loopback=True)


def test_parse_multipart():
    body = (b'--B\r\nContent-Disposition: form-data; name="room"\r\n\r\nkitchen\r\n'
            b'--B\r\nContent-Disposition: form-data; name="files"; filename="a.png"\r\n'
            b'Content-Type: image/png\r\n\r\n\x89PNGdata\r\n--B--\r\n')
    fields, files = parse_multipart("multipart/form-data; boundary=B", body)
    assert fields == {"room": "kitchen"} and files == [("files", "a.png", b"\x89PNGdata")]
