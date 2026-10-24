"""Fetch high-level chart data from sdvx.in into corpus/sdvxin/ (local research use only).

Newer charts are published as JSON; older ones as layered PNG images (notes/lasers,
lane background, bar lines). Both are stored as-is; `ksmauto.sdvxin` decodes them.
Nothing fetched here is redistributed (corpus/ is git-ignored). Requests are
sequential with a delay, and existing files are never re-downloaded.

Usage:
  uv run python scripts/fetch_sdvxin.py --levels 17-20 [--limit N] [--sample N] [--delay 1.0] [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import random
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "corpus" / "sdvxin"
BASE = "https://sdvx.in"
FOLDERS = ["01", "02", "03", "04", "05", "06", "07"]
DIFF_SUFFIX = {"nov": "n", "adv": "a", "exh": "e", "mxm": "m", "inf": "i", "grv": "g",
               "hvn": "h", "vvd": "v", "xcd": "x", "ult": "u"}
UA = "ksmauto-corpus/0.1 (personal research; low rate)"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


class Fetcher:
    def __init__(self, delay: float):
        self.delay = delay
        self.last = 0.0
        self.count = 0

    def get(self, path: str) -> tuple[int, bytes, str]:
        wait = self.last + self.delay - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self.last = time.monotonic()
        self.count += 1
        req = urllib.request.Request(BASE + path, headers={"User-Agent": UA})
        try:
            with _opener.open(req, timeout=30) as res:
                return res.status, res.read(), res.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            return e.code, b"", ""

    def save(self, path: str, dest: Path) -> bool:
        if dest.exists():
            return True
        status, body, _ = self.get(path)
        if status != 200 or not body:
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)
        return True


def parse_level(raw: str) -> float | None:
    if not raw or raw.startswith("_"):
        return None  # no chart page for this difficulty
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None
    return float(digits[:2] + "." + digits[2:]) if len(digits) == 3 else float(digits)


def candidates(fetcher: Fetcher, lo: float, hi: float) -> list[dict]:
    out = []
    for folder in FOLDERS:
        dest = OUT / f"songs{folder}.json"
        if not fetcher.save(f"/sdvx/_/json/songs{folder}.json", dest):
            continue
        for song in json.loads(dest.read_text(encoding="utf-8")):
            for diff, raw in song.get("levels", {}).items():
                level = parse_level(raw)
                if level is None or not lo <= level < hi + 1 or diff not in DIFF_SUFFIX:
                    continue
                out.append({"folder": folder, "id": song["id"], "diff": diff,
                            "key": song["id"] + DIFF_SUFFIX[diff], "level": level,
                            "title": song.get("title", ""), "artist": song.get("artist", ""),
                            "bpm": song.get("bpm", ""),
                            "counts": {k: song.get(k, {}).get(diff, "") for k in ("chip", "hold", "laser")}})
    return out


def fetch_chart(fetcher: Fetcher, c: dict) -> str:
    d = OUT / c["folder"] / c["key"]
    meta = d / "meta.json"
    if meta.exists():
        return "cached"
    d.mkdir(parents=True, exist_ok=True)
    status, body, ctype = fetcher.get(f"/sdvx/{c['folder']}/{c['key']}.json")
    if status == 200 and "json" in ctype:
        (d / "chart.json").write_bytes(body)
        kind = "json"
    else:
        data_js = OUT / c["folder"] / "js" / f"{c['id']}data.js"
        if not fetcher.save(f"/{c['folder']}/js/{c['id']}data.js", data_js):
            return "missing"
        text = data_js.read_text(encoding="utf-8", errors="replace")
        fn = re.search(rf"PNG{c['key'].upper()}\(\)\{{(.*?)\}}", text, re.S)
        if not fn:
            return "missing"
        images = re.findall(r"<img src=(/[^ >]+\.png)", fn.group(1))
        for src in images:
            if not fetcher.save(src, OUT / src.lstrip("/")):
                return "missing"
        c = {**c, "layers": [str((OUT / s.lstrip("/")).relative_to(OUT)) for s in images]}
        kind = "image"
    meta.write_text(json.dumps({**c, "kind": kind}, ensure_ascii=False, indent=1), encoding="utf-8")
    return kind


def main() -> None:
    global OUT
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--levels", default="17-20", help="level range, e.g. 17-20")
    p.add_argument("--limit", type=int, help="stop after this many charts")
    p.add_argument("--sample", type=int, help="random sample of this many charts (seeded)")
    p.add_argument("--delay", type=float, default=1.0, help="seconds between requests")
    p.add_argument("--out", type=Path, default=OUT, help="output directory (default corpus/sdvxin)")
    args = p.parse_args()
    OUT = args.out.resolve()
    lo, _, hi = args.levels.partition("-")
    fetcher = Fetcher(args.delay)
    cands = candidates(fetcher, float(lo), float(hi or lo))
    if args.sample:
        cands = random.Random(0).sample(cands, min(args.sample, len(cands)))
    if args.limit:
        cands = cands[: args.limit]
    print(f"{len(cands)} charts")
    stats: dict[str, int] = {}
    for i, c in enumerate(cands, 1):
        r = fetch_chart(fetcher, c)
        stats[r] = stats.get(r, 0) + 1
        if i % 20 == 0 or i == len(cands):
            print(f"{i}/{len(cands)} {stats} requests={fetcher.count}", flush=True)


if __name__ == "__main__":
    main()
