"""Vendor a KSM-WEB-VIEWER release as src/ksmauto/viewer.html.

    uv run python scripts/update_viewer.py v0.1.0
"""

from __future__ import annotations

import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL = "https://github.com/watanuki-azuma/KSM-WEB-VIEWER/releases/download/{tag}/index.html"


def main(tag: str) -> None:
    with urllib.request.urlopen(URL.format(tag=tag), timeout=30) as response:
        page = response.read()
    (ROOT / "src/ksmauto/viewer.html").write_bytes(page)
    preview = ROOT / "src/ksmauto/preview.py"
    text = re.sub(r'^VIEWER_VERSION = ".*"$', f'VIEWER_VERSION = "{tag}"', preview.read_text(), flags=re.M)
    preview.write_text(text)
    print(f"viewer.html <- {tag}")


if __name__ == "__main__":
    main(sys.argv[1])
