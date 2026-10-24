"""Self-contained HTML playback preview: chart and (optionally) audio in one file.

The page is KSM-WEB-VIEWER's released index.html (viewer.html, updated with
scripts/update_viewer.py), with the chart and audio written into its embed slots.
It needs no server, so it can be opened locally or shared as a single file.
"""

from __future__ import annotations

import base64
import html
import json
from pathlib import Path

VIEWER_VERSION = "v0.1.0"
AUDIO_TYPES = {".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".wav": "audio/wav", ".m4a": "audio/mp4"}
SLOTS = ("<title>Chart viewer</title>",
         '<script id="chart-data" type="application/json">null</script>',
         'const AUDIO_SRC = "";')


def build_preview(chart: dict, audio: str | Path | None = None) -> str:
    page = (Path(__file__).parent / "viewer.html").read_text(encoding="utf-8")
    for slot in SLOTS:
        if page.count(slot) != 1:
            raise ValueError(f"viewer.html {VIEWER_VERSION} has no embed slot {slot!r}")
    src = ""
    if audio:
        audio = Path(audio)
        mime = AUDIO_TYPES.get(audio.suffix.lower(), "application/octet-stream")
        src = f"data:{mime};base64," + base64.b64encode(audio.read_bytes()).decode("ascii")
    # Keep "</script>" in titles from closing the JSON block.
    data = json.dumps(chart, ensure_ascii=False).replace("</", "<\\/")
    title = chart.get("meta", {}).get("title") or "Chart viewer"
    values = (f"<title>{html.escape(title)}</title>",
              f'<script id="chart-data" type="application/json">{data}</script>',
              f"const AUDIO_SRC = {json.dumps(src)};")
    for slot, value in zip(SLOTS, values):
        page = page.replace(slot, value)
    return page
