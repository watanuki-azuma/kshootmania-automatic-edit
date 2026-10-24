"""Command-line interface: conversion, drafts, analysis, lint, and rendering."""

import argparse
import sys
from pathlib import Path

from .ksh import load_ksh
from .kson import load_kson, save_kson, validate
from .timing import TimingMap


def _load(path):
    suffix = path.suffix.lower()
    if suffix == ".ksh":
        return load_ksh(path)
    if suffix == ".ksmd":
        from .draft import compile_draft

        chart, errors = compile_draft(path.read_text(encoding="utf-8-sig"))
        if errors:
            raise ValueError("; ".join(f"{e.line}:{e.col}: {e.message}" for e in errors[:5]))
        return chart
    return load_kson(path)


def _measure_range(text):
    start, _, end = text.partition("-")
    return int(start), (int(end) + 1 if end else int(start) + 1)


def _chart_tools(args):
    """lint / stats / render: chart analysis commands that accept .kson, .ksh or .ksmd."""
    import json

    try:
        chart = _load(args.input)
        if args.command == "stats":
            from .lint import stats

            print(json.dumps(stats(chart), ensure_ascii=False))
            return 0
        if args.command == "lint":
            from .lint import lint

            analysis = json.loads(args.analysis.read_text(encoding="utf-8")) if args.analysis else None
            findings = lint(chart, analysis)
            for f in findings:
                print(f"{f.where}: {f.level}: {f.rule}: {f.message}")
            if not findings:
                print("no findings")
            return 0
        try:
            from .render import render
        except ImportError:
            print("install the render extra: uv sync --extra render", file=sys.stderr)
            return 1
        kw = {"measures_per_column": args.per_column, "columns_per_page": args.columns}
        if args.measures:
            kw["start"], kw["end"] = _measure_range(args.measures)
        output = args.output or args.input.with_suffix(".png")
        for path in render(chart, output, **kw):
            print(path)
        return 0
    except (OSError, ValueError) as exc:
        print(f"{args.input}: {exc}", file=sys.stderr)
        return 1


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
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "analyze":
        try:
            from .analyze import main as analyze_main
        except ImportError:
            print("install the audio extra: uv sync --extra audio", file=sys.stderr)
            return 1
        return analyze_main(argv[1:])
    if argv and argv[0] == "separate":
        from .separate import main as separate_main
        return separate_main(argv[1:])
    parser = argparse.ArgumentParser(prog="ksmauto")
    sub = parser.add_subparsers(dest="command", required=True)
    convert = sub.add_parser("convert", help="import a KSH chart as KSON")
    convert.add_argument("input", type=Path)
    convert.add_argument("-o", "--output", type=Path)
    sdvxin = sub.add_parser("sdvxin", help="decode a local sdvx.in chart or report on a corpus")
    sdvxin.add_argument("directory", type=Path)
    sdvxin.add_argument("-o", "--output", type=Path)
    sdvxin.add_argument("--report", action="store_true")
    for command in ("compile", "decompile"):
        draft = sub.add_parser(command)
        draft.add_argument("input", type=Path)
        draft.add_argument("-o", "--output", type=Path)
        if command == "compile":
            draft.add_argument("--base", type=Path)
    sub.add_parser("analyze", help="analyze audio (requires the audio extra)")
    sub.add_parser("separate", help="split audio into vocal/drum/bass/other stems (requires demucs)")
    lint_p = sub.add_parser("lint", help="report playability problems")
    lint_p.add_argument("input", type=Path)
    lint_p.add_argument("--analysis", type=Path, help="analysis JSON from `ksmauto analyze`")
    sub.add_parser("stats", help="density statistics and level estimate").add_argument("input", type=Path)
    render_p = sub.add_parser("render", help="draw the chart as PNG pages (requires the render extra)")
    render_p.add_argument("input", type=Path)
    render_p.add_argument("-o", "--output", type=Path)
    render_p.add_argument("--measures", help="measure range, e.g. 16-47")
    render_p.add_argument("--per-column", type=int, default=4)
    render_p.add_argument("--columns", type=int, default=8)
    edit = sub.add_parser("edit", help="preview and edit a chart in a local browser")
    edit.add_argument("input", type=Path)
    edit.add_argument("--audio", type=Path)
    edit.add_argument("--analysis", type=Path)
    edit.add_argument("--port", type=int, default=8765)
    edit.add_argument("--no-browser", action="store_true")
    preview = sub.add_parser("preview", help="write a self-contained HTML playback preview")
    preview.add_argument("input", type=Path)
    preview.add_argument("--audio", type=Path, help="embed this audio file (default: the chart's bgm, if found)")
    preview.add_argument("-o", "--output", type=Path, required=True)
    for command in ("validate", "info"):
        sub.add_parser(command).add_argument("files", type=Path, nargs="+")
    args = parser.parse_args(argv)
    if args.command == "sdvxin":
        from .sdvxin import load_sdvxin, report
        from .kson import dumps_kson

        try:
            if args.report:
                report(args.directory)
            else:
                chart = load_sdvxin(args.directory)
                if args.output:
                    save_kson(chart, args.output)
                else:
                    print(dumps_kson(chart), end="")
            return 0
        except ImportError:
            print("image decoding requires numpy and Pillow: uv sync --extra audio --extra render", file=sys.stderr)
            return 1
        except (OSError, ValueError, KeyError) as exc:
            print(f"{args.directory}: {exc}", file=sys.stderr)
            return 1
    if args.command == "edit":
        from .editor import run

        try:
            return run(args.input, audio=args.audio, analysis=args.analysis,
                       port=args.port, no_browser=args.no_browser)
        except (OSError, ValueError) as exc:
            print(f"{args.input}: {exc}", file=sys.stderr)
            return 1
    if args.command == "preview":
        from .preview import build_preview

        try:
            chart = _load(args.input)
            audio = args.audio
            bgm = chart.get("audio", {}).get("bgm", {}).get("filename")
            if audio is None and bgm and (args.input.parent / bgm).exists():
                audio = args.input.parent / bgm
            args.output.write_text(build_preview(chart, audio), encoding="utf-8")
        except (OSError, ValueError) as exc:
            print(f"{args.input}: {exc}", file=sys.stderr)
            return 1
        print(args.output)
        return 0
    if args.command in {"lint", "stats", "render"}:
        return _chart_tools(args)
    if args.command in {"compile", "decompile"}:
        from .draft import compile_draft, decompile

        try:
            if args.command == "compile":
                base = _load(args.base) if args.base else None
                chart, errors = compile_draft(args.input.read_text(encoding="utf-8-sig"), base)
                for error in errors:
                    print(f"{args.input}:{error.line}:{error.col}: {error.message}", file=sys.stderr)
                if errors:
                    return 1
                output = args.output or args.input.with_suffix(".kson")
                save_kson(chart, output)
                print(output)
            else:
                text, warnings = decompile(_load(args.input))
                for warning in warnings:
                    print(f"{args.input}: unsupported: {warning}", file=sys.stderr)
                if args.output:
                    args.output.write_text(text, encoding="utf-8")
                else:
                    print(text, end="")
            return 0
        except (OSError, ValueError) as exc:
            print(f"{args.input}: {exc}", file=sys.stderr)
            return 1
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
