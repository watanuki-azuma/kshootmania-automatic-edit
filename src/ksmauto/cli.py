"""Command-line chart conversion, validation, and summary."""

import argparse
import sys
from pathlib import Path

from .ksh import load_ksh
from .kson import load_kson, save_kson, validate
from .timing import TimingMap


def _load(path):
    return load_ksh(path) if path.suffix.lower() == ".ksh" else load_kson(path)


def _info(chart):
    meta = chart["meta"]
    print(f"{meta['title']} / {meta['artist']}")
    print(f"Difficulty: {meta['difficulty']}  Level: {meta['level']}")
    bpms = [v for _, v in chart["beat"]["bpm"]]
    print(f"BPM: {min(bpms):g}–{max(bpms):g}")
    end, slams, sections = 0, 0, 0
    for kind in ("bt", "fx"):
        chips, longs = 0, 0
        for lane in chart.get("note", {}).get(kind, []):
            for note in lane:
                y, length = (note, 0) if isinstance(note, int) else note
                chips += length == 0
                longs += length > 0
                end = max(end, y + length)
        print(f"{kind.upper()}: {chips} chips, {longs} longs")
    for lane in chart.get("note", {}).get("laser", []):
        sections += len(lane)
        for y, points, *width in lane:
            for ry, value, *curve in points:
                end = max(end, y + ry)
                slams += isinstance(value, list) and value[0] != value[1]
    print(f"Laser: {sections} sections, {slams} slams")
    print(f"Duration: {TimingMap(chart['beat']).pulse_to_sec(end):.3f} sec (through last note)")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="ksmauto")
    sub = parser.add_subparsers(dest="command", required=True)
    convert = sub.add_parser("convert", help="import a KSH chart as KSON")
    convert.add_argument("input", type=Path)
    convert.add_argument("-o", "--output", type=Path)
    for command in ("validate", "info"):
        sub.add_parser(command).add_argument("files", type=Path, nargs="+")
    args = parser.parse_args(argv)
    if args.command == "convert":
        try:
            chart = load_ksh(args.input)
            output = args.output or args.input.with_suffix(".kson")
            save_kson(chart, output)
            print(output)
            return 0
        except (OSError, ValueError) as exc:
            print(f"{args.input}: {exc}", file=sys.stderr)
            return 1
    status = 0
    for path in args.files:
        try:
            chart = _load(path)
            if args.command == "validate":
                issues = validate(chart)
                for issue in issues:
                    print(f"{path}: {issue.level}: {issue.path}: {issue.message}")
                status |= any(issue.level == "error" for issue in issues)
                if not issues:
                    print(f"{path}: OK")
            else:
                if len(args.files) > 1:
                    print(f"{path}:")
                errors = [i for i in validate(chart) if i.level == "error"]
                if errors:
                    raise ValueError(f"{errors[0].path}: {errors[0].message}")
                _info(chart)
        except (OSError, ValueError) as exc:
            print(f"{path}: {exc}", file=sys.stderr)
            status = 1
    return int(status)
