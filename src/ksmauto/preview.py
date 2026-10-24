"""Self-contained HTML playback preview: chart and (optionally) audio in one file.

The page needs no server, so it can be opened locally or shared as a single file.
"""

from __future__ import annotations

import base64
import html
import json
from pathlib import Path

AUDIO_TYPES = {".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".wav": "audio/wav", ".m4a": "audio/mp4"}


def build_preview(chart: dict, audio: str | Path | None = None) -> str:
    template = (Path(__file__).parent / "preview_template.html").read_text(encoding="utf-8")
    src = ""
    if audio:
        audio = Path(audio)
        mime = AUDIO_TYPES.get(audio.suffix.lower(), "application/octet-stream")
        src = f"data:{mime};base64," + base64.b64encode(audio.read_bytes()).decode("ascii")
    # Keep "</script>" in titles from closing the JSON block.
    data = json.dumps(chart, ensure_ascii=False).replace("</", "<\\/")
    title = chart.get("meta", {}).get("title") or "Chart preview"
    return (template.replace("__TITLE__", html.escape(title))
            .replace("__CHART_JSON__", data)
            .replace("__AUDIO_SRC__", src))
