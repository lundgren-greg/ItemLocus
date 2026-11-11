"""CLI argument handling and the localhost server."""
import http.client
import json
import re
import threading

import pytest

from conftest import BLUE, RED, FakeDetector, FakeEmbedder, scene
from itemlocus.cli import main
from itemlocus.web import PAGE, make_server

KEYS = (100, 100, 140, 130)


def cli(tmp, *argv):
    return main([*argv], detector_factory=FakeDetector, embedder_factory=FakeEmbedder)


def test_cli_ingest_enroll_find_json(tmp_path, capsys):
    photos = tmp_path / "photos"
    (photos / "kitchen").mkdir(parents=True)
    scene((RED, KEYS)).save(photos / "kitchen" / "a.png")
    ref = tmp_path / "ref.png"
    scene((RED, (50, 50, 90, 80))).save(ref)
    d = ["--data-dir", str(tmp_path / "data")]
    assert cli(tmp_path, "ingest", str(photos), *d) == 0
    assert cli(tmp_path, "enroll", "house keys", "--query", "keys", "--ref", str(ref), *d) == 0
    capsys.readouterr()
    assert cli(tmp_path, "find", "Where are my house keys?", "--json", *d) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "found" and out["room"] == "kitchen" and out["crop"].endswith(".jpg")
    assert cli(tmp_path, "items", *d) == 0 and "house keys" in capsys.readouterr().out
    assert cli(tmp_path, "forget", "house keys", *d) == 0
    assert cli(tmp_path, "find", "house keys", *d) == 2  # unknown item


def test_cli_not_sure_exit_code_and_text(tmp_path, capsys):
    scene((BLUE, KEYS)).save(tmp_path / "a.png")
    d = ["--data-dir", str(tmp_path / "data")]
    cli(tmp_path, "ingest", str(tmp_path / "a.png"), "--room", "office", *d)
    cli(tmp_path, "enroll", "keys", *d)
    scene().save(tmp_path / "b.png")
    cli(tmp_path, "ingest", str(tmp_path / "b.png"), *d)
    capsys.readouterr()
    cli(tmp_path, "enroll", "front keys", "--query", "keys", "--ref", str(tmp_path / "a.png"), *d)
    scene((RED, KEYS)).save(tmp_path / "r.png")
    cli(tmp_path, "enroll", "red keys", "--query", "keys", "--ref", str(tmp_path / "r.png"), *d)
    capsys.readouterr()
    assert cli(tmp_path, "find", "red keys", *d) == 1
    assert "not sure" in capsys.readouterr().out


@pytest.mark.parametrize("argv", [[], ["find"], ["enroll"], ["bogus"], ["serve", "--port", "x"], ["find", "k", "--threshold", "high"]])
def test_cli_bad_arguments_exit_2(argv):
    with pytest.raises(SystemExit) as e:
        main(argv)
    assert e.value.code == 2


def test_cli_validation_errors_are_clean(tmp_path, capsys):
    d = ["--data-dir", str(tmp_path / "data")]
    assert cli(tmp_path, "ingest", str(tmp_path / "missing"), *d) == 2
    assert cli(tmp_path, "enroll", "  ", *d) == 2
    assert cli(tmp_path, "enroll", "x", "--ref", str(tmp_path / "nope.png"), *d) == 2
    assert "error:" in capsys.readouterr().err


def test_serve_refuses_non_loopback(tmp_path, capsys):
    assert main(["serve", "--host", "0.0.0.0", "--data-dir", str(tmp_path)]) == 2
    assert "loopback" in capsys.readouterr().err


def multipart(fields, files):
    b = b"XBOUNDARYX"
    body = b""
    for k, v in fields.items():
        body += b'--' + b + b'\r\nContent-Disposition: form-data; name="' + k.encode() + b'"\r\n\r\n' + v.encode() + b"\r\n"
    for name, data in files:
        body += (b'--' + b + b'\r\nContent-Disposition: form-data; name="files"; filename="' + name.encode()
                 + b'"\r\nContent-Type: image/png\r\n\r\n' + data + b"\r\n")
    return body + b"--" + b + b"--\r\n", "multipart/form-data; boundary=XBOUNDARYX"


@pytest.fixture
def server(env):
    srv = make_server(env.cfg, "127.0.0.1", 0, FakeDetector, FakeEmbedder)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv
    srv.shutdown()
    srv.server_close()
    t.join(5)


def request(srv, method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10)
    c.request(method, path, body, headers or {})
    r = c.getresponse()
    data = r.read()
    c.close()
    return r.status, data


def png_bytes(img, tmp):
    p = tmp / "u.png"
    img.save(p)
    return p.read_bytes()


def test_server_page_has_no_external_assets():
    assert not re.search(r"(?:src|href|action)=[\"']?(?:https?:)?//", PAGE) and "@import" not in PAGE


def test_server_upload_enroll_find_and_traversal_rejected(env, server):
    data = png_bytes(scene((RED, KEYS)), env.tmp)
    for evil in ("../evil.png", "..\\evil.png", "/etc/passwd.png", "a/b.png"):
        body, ctype = multipart({"room": "kitchen"}, [(evil, data)])
        status, _ = request(server, "POST", "/api/upload", body, {"Content-Type": ctype, "Content-Length": str(len(body))})
        assert status == 400
    assert env.store.list_photos() == [] and not (env.tmp / "evil.png").exists()
    body, ctype = multipart({"room": "kitchen"}, [("shot.png", data)])
    status, out = request(server, "POST", "/api/upload", body, {"Content-Type": ctype})
    assert status == 200 and json.loads(out)["added"] == 1
    body, ctype = multipart({"name": "keys"}, [])
    assert request(server, "POST", "/api/enroll", body, {"Content-Type": ctype})[0] == 200
    status, out = request(server, "POST", "/api/find", json.dumps({"question": "where are my keys?"}),
                          {"Content-Type": "application/json"})
    ans = json.loads(out)
    assert status == 200 and ans["status"] == "found" and ans["room"] == "kitchen" and "candidates" not in ans
    assert request(server, "GET", ans["crop_url"])[0] == 200
    assert request(server, "GET", ans["photo_url"])[0] == 200
    assert request(server, "GET", "/files/photos/..%2f..%2fdata%2fitemlocus.db")[0] == 404
    assert request(server, "GET", "/files/crops/../itemlocus.db")[0] == 404


def test_server_rejects_foreign_host_and_origin(server):
    assert request(server, "GET", "/", headers={"Host": "evil.example"})[0] == 403
    assert request(server, "GET", "/")[0] == 200
    body = b"{}"
    port = server.server_address[1]
    hdr = {"Origin": "http://evil.example", "Content-Type": "application/json"}
    assert request(server, "POST", "/api/find", body, hdr)[0] == 403
    assert request(server, "GET", "/", headers={"Host": f"localhost:{port}"})[0] == 200
