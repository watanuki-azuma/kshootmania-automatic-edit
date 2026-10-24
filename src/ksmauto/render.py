"""Render KSON charts to PNG pages for visual self-checking (requires the `render` extra).

Layout follows the KSM editor: each column holds a few measures with time running
upwards; columns run left to right.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from .timing import TimingMap

PX_PER_PULSE = 0.25          # a 4/4 measure is 240 px tall
LANE_W = 22                  # BT lane width
LASER_MARGIN = 26            # laser travel outside the BT area on each side
GAP = 34                     # space between columns (measure numbers live here)
PAD = 16

BG = (14, 14, 22)
LANE_BG = (30, 30, 42)
BEAT_LINE = (58, 58, 74)
MEASURE_LINE = (150, 150, 170)
TEXT = (200, 200, 215)
BT = (240, 240, 240)
BT_LONG = (200, 200, 200)
FX = (255, 150, 30)
FX_LONG = (200, 110, 20)
LASER = [(30, 200, 255), (255, 60, 190)]


def _notes(lane):
    for note in lane:
        yield (note, 0) if isinstance(note, int) else (note[0], note[1])


def _value(v):
    return (v, v) if not isinstance(v, list) else (v[0], v[1])


def render_pages(chart: dict, measures_per_column: int = 4, columns_per_page: int = 8,
                 start: int = 0, end: int | None = None) -> list[Image.Image]:
    """Return one image per page covering measures [start, end)."""
    timing = TimingMap(chart["beat"])
    note = chart.get("note", {})
    last = 0
    for kind in ("bt", "fx"):
        for lane in note.get(kind, []):
            for y, length in _notes(lane):
                last = max(last, y + length)
    for lane in note.get("laser", []):
        for y, points, *_ in lane:
            last = max(last, y + points[-1][0])
    if end is None:
        end = timing.pulse_to_measure(last)[0] + 1
    per_page = measures_per_column * columns_per_page
    return [_render_page(chart, timing, m, min(m + per_page, end), measures_per_column)
            for m in range(start, end, per_page)]


def _render_page(chart, timing, m0, m1, per_col):
    inner = LANE_W * 4
    col_w = inner + 2 * LASER_MARGIN
    n_cols = -(-(m1 - m0) // per_col)
    col_heights = []
    for c in range(n_cols):
        a = m0 + c * per_col
        b = min(a + per_col, m1)
        col_heights.append((timing.measure_to_pulse(b) - timing.measure_to_pulse(a)) * PX_PER_PULSE)
    height = int(max(col_heights) + 2 * PAD + 14)
    width = int(n_cols * (col_w + GAP) + PAD * 2)
    img = Image.new("RGB", (width, height), BG)
    d = ImageDraw.Draw(img, "RGBA")
    note = chart.get("note", {})
    title = chart.get("meta", {}).get("title", "")
    d.text((PAD, 2), f"{title}  m{m0}-{m1 - 1}", fill=TEXT)

    for c in range(n_cols):
        a = m0 + c * per_col
        b = min(a + per_col, m1)
        p0, p1 = timing.measure_to_pulse(a), timing.measure_to_pulse(b)
        # Each column is drawn on its own layer so notes crossing its ends are clipped.
        col_x = PAD + GAP + c * (col_w + GAP)
        col = Image.new("RGBA", (col_w, height - PAD - 14), BG + (255,))
        cd = ImageDraw.Draw(col, "RGBA")
        x0 = 0
        bt_x = x0 + LASER_MARGIN
        base = col.height

        def py(pulse):
            return base - (pulse - p0) * PX_PER_PULSE

        cd.rectangle([bt_x, py(p1), bt_x + inner, base], fill=LANE_BG)
        for m in range(a, b + 1):
            mp = timing.measure_to_pulse(m)
            if m < b:
                nxt = timing.measure_to_pulse(m + 1)
                _, (n, den) = _sig_at(chart, m)
                step = 960 // den
                for bp in range(int(mp) + step, int(nxt), step):
                    cd.line([bt_x, py(bp), bt_x + inner, py(bp)], fill=BEAT_LINE)
                d.text((col_x - GAP + 4, 14 + py(mp) - 12), str(m), fill=TEXT)
            cd.line([bt_x - 6, py(mp), bt_x + inner + 6, py(mp)], fill=MEASURE_LINE, width=1)
        for i in range(1, 4):
            cd.line([bt_x + i * LANE_W, py(p1), bt_x + i * LANE_W, base], fill=BEAT_LINE)

        def visible(y, length):
            return y < p1 and y + length >= p0

        # FX first so BT draws on top.
        for lane, notes in enumerate(note.get("fx", [])):
            lx = bt_x + lane * 2 * LANE_W
            for y, length in _notes(notes):
                if not visible(y, length):
                    continue
                if length:
                    cd.rectangle([lx + 2, py(min(y + length, p1)), lx + 2 * LANE_W - 2, py(max(y, p0))], fill=FX_LONG + (150,))
                else:
                    cd.rectangle([lx + 1, py(y) - 4, lx + 2 * LANE_W - 1, py(y)], fill=FX)
        for lane, notes in enumerate(note.get("bt", [])):
            lx = bt_x + lane * LANE_W
            for y, length in _notes(notes):
                if not visible(y, length):
                    continue
                if length:
                    cd.rectangle([lx + 4, py(min(y + length, p1)), lx + LANE_W - 4, py(max(y, p0))], fill=BT_LONG)
                else:
                    cd.rectangle([lx + 2, py(y) - 4, lx + LANE_W - 2, py(y)], fill=BT)

        for side, sections in enumerate(note.get("laser", [])):
            color = LASER[side]
            for y, points, *w in sections:
                wide = (w[0] if w else 1) == 2

                def lx(v, wide=wide):
                    if wide:
                        return x0 + (v * col_w)
                    return bt_x - LASER_MARGIN / 2 + v * (inner + LASER_MARGIN)

                pts = [(y + ry, *_value(v)) for ry, v, *_ in points]
                if pts[-1][0] < p0 or pts[0][0] >= p1:
                    continue
                for (ya, va, vfa), (yb, vb, _) in zip(pts, pts[1:]):
                    cd.line([lx(vfa), py(ya), lx(vb), py(yb)], fill=color + (220,), width=6)
                for ya, va, vfa in pts:
                    if va != vfa:
                        cd.rectangle([min(lx(va), lx(vfa)) - 3, py(ya) - 10, max(lx(va), lx(vfa)) + 3, py(ya)], fill=color + (230,))
        img.paste(col, (col_x, 14))
    return img


def _sig_at(chart, measure):
    sig = [0, [4, 4]]
    for s in chart["beat"].get("time_sig", [[0, [4, 4]]]):
        if s[0] <= measure:
            sig = s
    return sig[0], tuple(sig[1])


def render(chart: dict, out: str | Path, **kw) -> list[Path]:
    """Write `out` (single page) or `out_000.png`, `out_001.png`, ... and return the paths."""
    out = Path(out)
    pages = render_pages(chart, **kw)
    paths = [out] if len(pages) == 1 else [out.with_name(f"{out.stem}_{i:03d}{out.suffix or '.png'}") for i in range(len(pages))]
    for img, p in zip(pages, paths):
        img.save(p)
    return paths
