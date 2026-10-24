"""Render a decoded sdvx.in chart next to its source image layers (local check only).

Usage: uv run python tests/eval/sdvxin_side_by_side.py corpus/sdvxin/04/04064m [-o out/sdvxin/04064m.png]
"""

import argparse
import json
from pathlib import Path

from PIL import Image

from ksmauto.render import render_pages
from ksmauto.sdvxin import load_sdvxin


def side_by_side(chart_dir: Path, out: Path) -> Path:
    meta = json.loads((chart_dir / 'meta.json').read_text(encoding='utf-8'))
    chart = load_sdvxin(chart_dir)
    pages = render_pages(chart, measures_per_column=4, columns_per_page=200)
    right = pages[0]
    if meta['kind'] == 'image':
        root = chart_dir.parent.parent
        layers = [Image.open(root / p).convert('RGBA') for p in meta['layers']]
        size = (max(l.width for l in layers), max(l.height for l in layers))
        left = Image.new('RGBA', size, (0, 0, 0, 255))
        for layer in layers:  # bg, obj, bar as the viewer stacks them
            left.alpha_composite(layer)
    else:
        left = Image.new('RGBA', (1, right.height), (0, 0, 0, 255))
    canvas = Image.new('RGB', (left.width + right.width + 20, max(left.height, right.height)), (40, 40, 40))
    canvas.paste(left.convert('RGB'), (0, 0))
    canvas.paste(right.convert('RGB'), (left.width + 20, 0))
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('chart_dir', type=Path)
    parser.add_argument('-o', '--output', type=Path)
    args = parser.parse_args()
    print(side_by_side(args.chart_dir, args.output or Path('out/sdvxin') / f'{args.chart_dir.name}.png'))


if __name__ == '__main__':
    main()
