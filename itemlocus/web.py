"""Minimal localhost page (stdlib only, no external assets). Loopback only by default."""
from __future__ import annotations

import ipaddress
import json
import re
from email.parser import BytesParser
from email import policy
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

from PIL import Image

from . import query as query_mod
from .config import Config
from .enroll import enroll
from .ingest import clean_label, ingest_upload, safe_filename
from .store import Store

MAX_BODY = 100 * 1024 * 1024
LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]"}
CROP_RE = re.compile(r"^[a-z0-9-]{1,40}\.jpg$")
PHOTO_RE = re.compile(r"^[0-9a-f]{16}\.jpg$")
CSP = ("default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; "
       "script-src 'unsafe-inline'; connect-src 'self'; form-action 'none'")

PAGE = """<!doctype html><html lang="en"><meta charset="utf-8"><title>ItemLocus photo test</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{font:18px system-ui;max-width:46rem;margin:1rem auto;padding:0 1rem}
fieldset{margin:1rem 0}input,button{font:inherit;margin:.2rem 0}
.wrap{position:relative;display:inline-block}.wrap img{max-width:100%}
.box{position:absolute;border:3px solid #d00;box-sizing:border-box}#out img{max-width:100%}</style>
<h1>ItemLocus photo test</h1>
<p>Everything stays on this computer. Photos are cleaned (metadata removed, people blacked out) before they are saved.</p>
<fieldset><legend>1. Add room photos</legend>
<input id="room" placeholder="Room (optional)"><br>
<input id="files" type="file" accept="image/*" multiple><br><button onclick="upload()">Add photos</button></fieldset>
<fieldset><legend>2. Enroll an item</legend>
<input id="name" placeholder="Name, e.g. house keys"><br>
<input id="q" placeholder="What to look for, e.g. keys (optional)"><br>
<input id="refs" type="file" accept="image/*" multiple><br><button onclick="enroll()">Enroll</button></fieldset>
<fieldset><legend>3. Ask</legend>
<input id="ask" placeholder="Where are my keys?" size="30"> <button onclick="find()">Ask</button></fieldset>
<p id="status" role="status"></p><div id="out"></div><p id="state"></p>
<script>
const $=id=>document.getElementById(id);
async function post(url,body,json){const r=await fetch(url,{method:'POST',body:json?JSON.stringify(body):body,
 headers:json?{'Content-Type':'application/json'}:{}});const d=await r.json();
 if(!r.ok)throw new Error(d.error||r.statusText);return d}
function say(t){$('status').textContent=t}
function form(extra,input){const f=new FormData();for(const k in extra)f.append(k,extra[k]);
 for(const file of input.files)f.append('files',file,file.name);return f}
async function state(){const d=await (await fetch('/api/state')).json();
 $('state').textContent=d.photos+' photo(s); items: '+(d.items.join(', ')||'none')}
async function upload(){say('Working (first run loads models)...');try{const d=await post('/api/upload',form({room:$('room').value},$('files')));
 say('Added '+d.added+' photo(s); '+d.people_masked+' had people blacked out.');state()}catch(e){say('Error: '+e.message)}}
async function enroll(){say('Working...');try{const d=await post('/api/enroll',form({name:$('name').value,query:$('q').value},$('refs')));
 say('Enrolled '+d.name+' with '+d.refs_added+' reference photo(s). '+d.notes.join(' '));state()}catch(e){say('Error: '+e.message)}}
async function find(){say('Looking...');$('out').replaceChildren();try{const d=await post('/api/find',{question:$('ask').value},true);
 say(d.message);if(d.status!=='found')return;const o=$('out'),w=document.createElement('div');w.className='wrap';
 const im=document.createElement('img');im.src=d.photo_url;im.alt='Matching photo';const b=document.createElement('div');b.className='box';
 const [x0,y0,x1,y1]=d.box,[W,H]=d.image_size;Object.assign(b.style,{left:100*x0/W+'%',top:100*y0/H+'%',width:100*(x1-x0)/W+'%',height:100*(y1-y0)/H+'%'});
 w.append(im,b);const c=document.createElement('img');c.src=d.crop_url;c.alt='Cropped item';c.style.maxHeight='10rem';
 const p=document.createElement('p');p.textContent='Room: '+(d.room||'not labelled')+' | confidence '+Math.round(100*d.confidence)+'%';o.append(p,w,document.createElement('br'),c)}catch(e){say('Error: '+e.message)}}
state()
</script></html>"""


def check_bind_host(host: str, allow_non_loopback: bool = False) -> None:
    """Refuse anything but loopback unless the caller explicitly accepts the risk."""
    if allow_non_loopback or host == "localhost":
        return
    try:
        if ipaddress.ip_address(host).is_loopback:
            return
    except ValueError:
        pass
    raise ValueError(f"refusing to bind to '{host}': this page has no login and is loopback-only. "
                     "Use --allow-non-loopback-UNSAFE only on a network you fully trust.")


def parse_multipart(content_type: str, body: bytes):
    """Return (fields, files) where files is a list of (field, filename, bytes)."""
    msg = BytesParser(policy=policy.default).parsebytes(
        b"MIME-Version: 1.0\r\nContent-Type: " + content_type.encode("latin-1") + b"\r\n\r\n" + body)
    if not msg.is_multipart():
        raise ValueError("expected multipart form data")
    fields, files = {}, []
    for part in msg.iter_parts():
        name, filename = part.get_param("name", header="content-disposition"), part.get_filename()
        data = part.get_payload(decode=True) or b""
        if filename is not None:
            files.append((name, filename, data))
        else:
            fields[name] = data.decode("utf-8", "replace")
    return fields, files


class App:
    def __init__(self, cfg: Config, detector_factory, embedder_factory, unsafe: bool = False):
        self.cfg, self.unsafe = cfg, unsafe
        self._factories, self._models = (detector_factory, embedder_factory), [None, None]

    def model(self, i: int):
        if self._models[i] is None:
            self._models[i] = self._factories[i]()
        return self._models[i]

    detector = property(lambda s: s.model(0))
    embedder = property(lambda s: s.model(1))


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        server_version = "ItemLocus"

        def log_message(self, *a):  # no request logging: it could include file names
            pass

        def _send(self, code, body: bytes, ctype="application/json"):
            self.send_response(code)
            for k, v in (("Content-Type", ctype), ("Content-Length", str(len(body))), ("Cache-Control", "no-store"),
                         ("Content-Security-Policy", CSP), ("X-Content-Type-Options", "nosniff")):
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code, obj):
            self._send(code, json.dumps(obj).encode())

        def _allowed(self) -> bool:
            if app.unsafe:
                return True
            host = self.headers.get("Host", "")
            origin = self.headers.get("Origin")
            ok = host.rsplit(":", 1)[0] in LOCAL_HOSTS if not host.endswith("]") else host in LOCAL_HOSTS
            return ok and (origin is None or urlparse(origin).netloc == host)  # blocks DNS rebinding / cross-site posts

        def do_GET(self):
            if not self._allowed():
                return self._json(403, {"error": "forbidden host"})
            path = urlparse(self.path).path
            if path == "/":
                return self._send(200, PAGE.encode(), "text/html; charset=utf-8")
            if path == "/api/state":
                store = Store(app.cfg.db_path)
                try:
                    return self._json(200, {"photos": len(store.list_photos()), "items": store.list_items()})
                finally:
                    store.close()
            for prefix, rx, folder in (("/files/crops/", CROP_RE, app.cfg.crops_dir),
                                       ("/files/photos/", PHOTO_RE, app.cfg.indexed_dir)):
                if path.startswith(prefix) and rx.match(path[len(prefix):]):
                    f = folder / path[len(prefix):]
                    if f.is_file():
                        return self._send(200, f.read_bytes(), "image/jpeg")
            self._json(404, {"error": "not found"})

        def do_POST(self):
            if not self._allowed():
                return self._json(403, {"error": "forbidden host"})
            try:
                length = int(self.headers.get("Content-Length", ""))
                if not 0 <= length <= MAX_BODY:
                    raise ValueError("request too large")
                body = self.rfile.read(length)
                self._json(200, self._route(urlparse(self.path).path, body))
            except ImportError:
                self._json(500, {"error": "model libraries are not installed (see README: Try the photo test)"})
            except (ValueError, OSError, Image.DecompressionBombError) as e:
                self._json(400, {"error": str(e)})

        def _route(self, path, body):
            cfg, ctype = app.cfg, self.headers.get("Content-Type", "")
            cfg.ensure()
            store = Store(cfg.db_path)
            try:
                if path == "/api/upload":
                    fields, files = parse_multipart(ctype, body)
                    room = clean_label(fields["room"], "room", 60) if fields.get("room", "").strip() else None
                    for _, fn, _ in files:
                        safe_filename(fn)  # validate every name before doing any work
                    recs = [ingest_upload(d, fn, room, store, cfg, app.detector) for _, fn, d in files]
                    return {"added": len(recs), "people_masked": sum(1 for r in recs if r.masks)}
                if path == "/api/enroll":
                    fields, files = parse_multipart(ctype, body)
                    for _, fn, _ in files:
                        safe_filename(fn)
                    r = enroll(fields.get("name", ""), [d for _, _, d in files], store, app.detector,
                               app.embedder, fields.get("query", "").strip() or None)
                    return {"name": r.name, "refs_added": r.refs_added, "notes": r.notes}
                if path == "/api/find":
                    q = json.loads(body or b"{}").get("question", "")
                    ans = query_mod.find(q, store, cfg, app.detector, app.embedder).to_dict()
                    if ans["status"] == "found":
                        ans["crop_url"] = f"/files/crops/{ans['crop']}"
                        ans["photo_url"] = f"/files/photos/{ans['photo_id']}.jpg"
                    ans.pop("candidates", None)
                    return ans
                raise ValueError("unknown endpoint")
            finally:
                store.close()

    return Handler


def make_server(cfg: Config, host: str, port: int, detector_factory, embedder_factory,
                allow_non_loopback: bool = False) -> HTTPServer:
    check_bind_host(host, allow_non_loopback)
    return HTTPServer((host, port), make_handler(App(cfg, detector_factory, embedder_factory, allow_non_loopback)))
