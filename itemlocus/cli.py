"""Command line: ingest, enroll, find, items, forget, serve."""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import ranking
from .config import Config


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--photos-dir", help="default photo folder (env ITEMLOCUS_PHOTOS, default photos/)")
    common.add_argument("--data-dir", help="database, indexed copies, crops (env ITEMLOCUS_DATA, default data/)")
    models = argparse.ArgumentParser(add_help=False)
    models.add_argument("--detector", choices=["owlv2", "yoloworld"], default="owlv2")
    models.add_argument("--embedder", choices=["clip", "dinov2"], default="clip")
    models.add_argument("--device", help="cpu or cuda; default: cuda if torch sees it, else cpu")

    p = argparse.ArgumentParser(prog="itemlocus", description="Find items in a few local photos. Nothing is uploaded.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("ingest", parents=[common, models], help="add room photos (metadata stripped, people masked)")
    s.add_argument("paths", nargs="*", help="files or folders (default: the photos folder)")
    s.add_argument("--room", help="room label; default: sub-folder name, if any")

    s = sub.add_parser("enroll", parents=[common, models], help="enroll an item, optionally with reference photos")
    s.add_argument("name")
    s.add_argument("--ref", action="append", default=[], metavar="PHOTO", help="reference photo (repeatable)")
    s.add_argument("--query", help="what the detector should look for (default: the name), e.g. keys")

    s = sub.add_parser("find", parents=[common, models], help='ask, e.g. find "keys" or find "where are my keys?"')
    s.add_argument("question")
    s.add_argument("--json", action="store_true", help="machine-readable output, including candidate scores")
    s.add_argument("--verbose", action="store_true", help="also print candidate scores")
    s.add_argument("--threshold", type=float, default=float(os.environ.get("ITEMLOCUS_THRESHOLD", ranking.DEFAULT_THRESHOLD)))
    s.add_argument("--margin", type=float, default=ranking.DEFAULT_MARGIN)

    sub.add_parser("items", parents=[common], help="list enrolled items")
    s = sub.add_parser("forget", parents=[common], help="delete an enrolled item")
    s.add_argument("name")

    s = sub.add_parser("serve", parents=[common, models], help="local web page on 127.0.0.1")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--allow-non-loopback-UNSAFE", dest="unsafe", action="store_true",
                   help="UNSAFE: allow binding a non-loopback address. The page has no login.")
    return p


def main(argv=None, detector_factory=None, embedder_factory=None) -> int:
    args = build_parser().parse_args(argv)
    cfg = Config.resolve(args.photos_dir, args.data_dir)
    load_det = detector_factory or (lambda: _models().load_detector(args.detector, args.device))
    load_emb = embedder_factory or (lambda: _models().load_embedder(args.embedder, args.device))
    try:
        return _run(args, cfg, load_det, load_emb)
    except (ValueError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except ImportError as e:
        print(f"error: model libraries missing ({e.name}). Install requirements.txt; see README.", file=sys.stderr)
        return 2


def _models():
    from . import models

    return models


def _run(args, cfg: Config, load_det, load_emb) -> int:
    from . import enroll as enroll_mod, ingest, query
    from .store import Store

    if args.cmd == "serve":
        from .web import make_server

        server = make_server(cfg, args.host, args.port, load_det, load_emb, args.unsafe)
        print(f"Serving on http://{args.host}:{args.port}/  (Ctrl+C to stop)")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        return 0

    cfg.ensure()
    store = Store(cfg.db_path)
    try:
        if args.cmd == "ingest":
            recs, skipped = ingest.ingest_paths(args.paths or [cfg.photos_dir], args.room, store, cfg, load_det())
            masked = sum(1 for r in recs if r.masks)
            print(f"Ingested {len(recs)} photo(s); {masked} had people blacked out; {len(skipped)} skipped.")
            for name in skipped:
                print(f"  skipped (not an image): {name}")
        elif args.cmd == "enroll":
            r = enroll_mod.enroll(args.name, args.ref, store, load_det(), load_emb(), args.query)
            kind = f"{r.refs_added} reference photo(s)" if r.refs_added else "text only"
            print(f"Enrolled '{r.name}' (detector query: '{r.query}', {kind}).")
            for n in r.notes:
                print(f"  note: {n}")
        elif args.cmd == "find":
            ans = query.find(args.question, store, cfg, load_det(), load_emb(), args.threshold, args.margin)
            if args.json:
                d = ans.to_dict()
                d["crop"] = str(cfg.crops_dir / ans.crop) if ans.crop else None
                print(json.dumps(d, indent=2))
            else:
                print(ans.message)
                if ans.status == "found":
                    print(f"  box (x0,y0,x1,y1): {tuple(round(v) for v in ans.box)}   crop: {cfg.crops_dir / ans.crop}")
                if args.verbose:
                    for c in ans.candidates:
                        print(f"  candidate: photo {c['photo_id'][:8]} room={c['room']} conf={c['confidence']:.2f} sim={c['sim']}")
            return 0 if ans.status == "found" else (2 if ans.status == "unknown_item" else 1)
        elif args.cmd == "items":
            for n in store.list_items():
                print(n)
        elif args.cmd == "forget":
            print("Deleted." if store.delete_item(args.name) else "No such item.")
        return 0
    finally:
        store.close()
