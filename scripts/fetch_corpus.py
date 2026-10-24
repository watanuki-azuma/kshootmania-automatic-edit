"""Download the official K-Shoot MANIA package and extract its bundled songs into corpus/.

The charts and audio are not redistributed by this repository; they are fetched
locally for testing and evaluation only.

Usage: uv run python scripts/fetch_corpus.py [--zip PATH]
"""

from __future__ import annotations

import argparse
import shutil
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus" / "official"
URL = "https://www.kshootmania.com/dl/kshootmania_v2.1.0_win.zip"
SONGS_PREFIX = "kshootmania_v2/songs/"
KEEP_SUFFIXES = {".ksh", ".kson", ".ogg", ".mp3", ".wav", ".flac", ".jpg", ".png"}


def extract_songs(zip_path: Path, dest: Path) -> int:
    count = 0
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            name = PurePosixPath(info.filename)
            if info.is_dir() or not info.filename.startswith(SONGS_PREFIX):
                continue
            if name.suffix.lower() not in KEEP_SUFFIXES:
                continue
            rel = PurePosixPath(*name.parts[2:])
            if ".." in rel.parts or rel.is_absolute():
                continue
            out = dest / Path(*rel.parts)
            out.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(out, "wb") as dst:
                shutil.copyfileobj(src, dst)
            count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, help="use an already downloaded package")
    args = parser.parse_args()

    zip_path = args.zip
    if zip_path is None:
        zip_path = ROOT / "corpus" / "kshootmania_win.zip"
        if not zip_path.exists():
            zip_path.parent.mkdir(parents=True, exist_ok=True)
            print(f"downloading {URL}")
            urllib.request.urlretrieve(URL, zip_path)
    n = extract_songs(zip_path, CORPUS)
    print(f"extracted {n} files into {CORPUS}")


if __name__ == "__main__":
    main()
