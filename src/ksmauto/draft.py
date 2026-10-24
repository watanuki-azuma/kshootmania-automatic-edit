"""Compile and decompile the line-oriented .ksmd chart draft format."""

import copy
import json
import math
import re
from dataclasses import dataclass
from fractions import Fraction

from .kson import _EFFECT_DEFAULTS, validate


@dataclass(frozen=True)
class DraftError:
    line: int
    col: int
    message: str


_META = {"title": "title", "artist": "artist", "chart_author": "chart_author",
         "difficulty": "difficulty", "level": "level", "jacket": "jacket_filename",
         "disp_bpm": "disp_bpm"}
_BGM = {"audio": "filename", "offset": "offset", "volume": "vol", "preview": "preview"}
_LANES = {name: ("bt", i) for i, name in enumerate("ABCD")}
_LANES.update({name: ("fx", i) for i, name in enumerate("LR")})
# Names usable without a `def` (KSON spec: predefined audio effects, FX key sounds).
_FX_EFFECTS = {"retrigger", "gate", "flanger", "pitch_shift", "bitcrusher", "phaser", "wobble", "tapestop",
               "echo", "sidechain"}
_LASER_EFFECTS = {"peaking_filter", "high_pass_filter", "low_pass_filter", "bitcrusher"}
_KEY_SOUNDS = {"clap", "clap_impact", "clap_punchy", "snare", "snare_lo"}
_EFFECT_TYPES = set(_EFFECT_DEFAULTS) | {"switch_audio"}


def _uncomment(line):
    quoted, escaped = False, False
    for i, char in enumerate(line):
        if escaped:
            escaped = False
        elif char == "\\" and quoted:
            escaped = True
        elif char == '"':
            quoted = not quoted
        elif char == "#" and not quoted:
            return line[:i]
    return line


def _string(value):
    if value.startswith('"'):
        result = json.loads(value)
        if not isinstance(result, str):
            raise ValueError("Expected a quoted string")
        return result
    return value


def _fraction(value):
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+|\d+/\d+)(?:\+\d+/\d+)?", value):
        raise ValueError(f"Invalid beat: {value!r}")
    try:
        return sum((Fraction(v) for v in value.lstrip("+").split("+")), Fraction())
    except (ValueError, ZeroDivisionError):
        raise ValueError(f"Invalid beat: {value!r}") from None


def _number(value):
    try:
        number = float(value)
    except ValueError:
        raise ValueError(f"Invalid number: {value!r}") from None
    if not math.isfinite(number):
        raise ValueError("Number must be finite")
    return number


def _signature(value):
    match = re.fullmatch(r"(\d+)/(\d+)", value)
    if not match or any(int(v) <= 0 for v in match.groups()):
        raise ValueError("Time signature must be positive N/D")
    return [int(v) for v in match.groups()]


def _sig_at(measure, signatures):
    result = [4, 4]
    for idx, sig in signatures:
        if idx > measure:
            break
        result = sig
    return result


def _start(measure, signatures):
    pulse, previous, length = Fraction(), 0, Fraction(960)
    for idx, (n, d) in signatures:
        if idx > measure:
            break
        pulse += (idx - previous) * length
        previous, length = idx, Fraction(960 * n, d)
    return pulse + (measure - previous) * length


def _locate(pulse, signatures):
    previous, start, sig = 0, Fraction(), [4, 4]
    for idx, next_sig in signatures:
        end = start + (idx - previous) * Fraction(960 * sig[0], sig[1])
        if pulse < end:
            break
        previous, start, sig = idx, end, next_sig
    count, offset = divmod(pulse - start, Fraction(960 * sig[0], sig[1]))
    return previous + int(count), offset / Fraction(960, sig[1])


def _rounded(value):
    result = round(value)
    if abs(value - result) >= 1:
        raise ValueError("Position rounding error is at least one pulse")
    return result


def _bounds(kind, note):
    if isinstance(note, int):
        return note, note
    y = note[0]
    return y, y + (note[1][-1][0] if kind == "laser" else note[1])


def _without_curves(section):
    return [section[0], [p[:2] for p in section[1]], *section[2:]]


def _note_key(kind, note):
    if kind != "laser":
        return [note, 0] if isinstance(note, int) else note
    return [note[0], [[p[0], p[1] if isinstance(p[1], list) else [p[1], p[1]]]
                      for p in note[1]], note[2] if len(note) > 2 else 1]


def _params(text):
    """`k=v,k=v` -> dict (values stay strings, as KSON stores them)."""
    params = {}
    for field in filter(None, text.split(",")):
        key, sep, value = field.partition("=")
        if not sep or not re.fullmatch(r"[a-z_0-9]+", key) or not value:
            raise ValueError(f"Expected KEY=VALUE, got {field!r}")
        params[key] = value
    return params


def _tag(token):
    """Split `L~2@gate(wave_length=1/16)` into the note part, effect name and params."""
    note, at, rest = token.partition("@")
    if not at:
        return token, None, None
    match = re.fullmatch(r"([A-Za-z0-9_.\-]+)(?:\((.*)\))?", rest)
    if not match:
        raise ValueError(f"Expected @NAME or @NAME(KEY=VALUE,...): {token!r}")
    return note, "" if match[1] == "-" else match[1], _params(match[2] or "")


def _format_tag(name, params):
    if params is None:
        return ""
    return f"@{name or '-'}" + (f"({','.join(f'{k}={v}' for k, v in params.items())})" if params else "")


def compile_draft(text: str, base: dict | None = None) -> tuple[dict, list[DraftError]]:
    """Collect syntax and semantic errors while building a possibly partial chart."""
    chart = copy.deepcopy(base) if base is not None else {}
    chart.setdefault("format_version", 1)
    meta = chart.setdefault("meta", {})
    for key, default in (("artist", ""), ("chart_author", ""), ("difficulty", 2), ("level", 1)):
        meta.setdefault(key, default)
    errors, statements, labels = [], [], []
    headers, signatures, bpms = {}, {}, {}
    defs = {"fx": [], "laser": []}
    fx_tags, laser_events = {}, []   # (lane, y) -> (name, params, line, col); [y, name, line, col]
    fx_switches = []                 # [y, lane, name, params, line, col]: effect changes inside long FX
    current = None

    def error(line, col, message):
        errors.append(DraftError(line, col, str(message)))

    for line_no, raw in enumerate(text.removeprefix("\ufeff").splitlines(), 1):
        line = _uncomment(raw).strip()
        col = len(raw) - len(raw.lstrip()) + 1
        if not line:
            continue
        try:
            if line.split()[0] == "def":
                parts = line.split()
                if len(parts) < 4 or parts[1] not in ("fx", "laser"):
                    raise ValueError("Expected def fx|laser NAME TYPE [KEY=VALUE ...]")
                if parts[3] not in _EFFECT_TYPES:
                    raise ValueError(f"Unknown audio effect type: {parts[3]}")
                params = _params(",".join(parts[4:]))
                definition = {"type": parts[3], **({"v": params} if params else {})}
                defs[parts[1]] = [d for d in defs[parts[1]] if d[0] != parts[2]] + [[parts[2], definition]]
            elif line.startswith("@m"):
                match = re.fullmatch(r'@m(\d+)(?:\s+(".*"))?', line)
                if not match:
                    raise ValueError('Expected @mN or @mN "label"')
                current = int(match[1])
                if match[2] is not None:
                    labels.append((current, _string(match[2])))
            elif current is None:
                if ":" not in line:
                    raise ValueError("Expected key: value header or @mN")
                key, value = (v.strip() for v in line.split(":", 1))
                if key not in {*_META, *_BGM, "bpm", "time_sig"}:
                    raise ValueError(f"Unknown header key: {key}")
                value = _string(value)
                if key in {"difficulty", "level", "offset"}:
                    value = int(value)
                    if key == "difficulty" and not 0 <= value <= 3:
                        raise ValueError("Difficulty must be an integer in 0..3")
                    if key == "level" and not 1 <= value <= 20:
                        raise ValueError("Level must be an integer in 1..20")
                elif key in {"volume", "bpm"}:
                    value = _number(value)
                    if key == "bpm" and value <= 0:
                        raise ValueError("BPM must be positive")
                elif key == "preview":
                    parts = value.split()
                    if len(parts) != 2 or any(not p.isdecimal() for p in parts):
                        raise ValueError("Preview must be OFFSET DURATION in nonnegative ms")
                    value = dict(zip(("offset", "duration"), map(int, parts)))
                elif key == "time_sig":
                    value = _signature(value)
                headers[key] = value
            elif line.split()[0] == "time_sig":
                parts = line.split()
                if len(parts) != 2:
                    raise ValueError("Expected time_sig N/D")
                signatures[current] = _signature(parts[1])
            else:
                tokens = [(m[0], col + m.start()) for m in re.finditer(r"\S+", line)]
                statements.append((line_no, current, tokens))
        except ValueError as exc:
            error(line_no, col, exc)

    for key in ("title", "bpm"):
        if key not in headers:
            error(1, 1, f"Required header is missing or invalid: {key}")
    for key, value in headers.items():
        if key in _META:
            meta[_META[key]] = value
        elif key in _BGM:
            chart.setdefault("audio", {}).setdefault("bgm", {})[_BGM[key]] = value
    signatures.setdefault(0, headers.get("time_sig", [4, 4]))
    sigs = [[m, sig] for m, sig in sorted(signatures.items())]
    if "bpm" in headers:
        bpms[0] = headers["bpm"]
    notes = {"bt": [[] for _ in range(4)], "fx": [[], []], "laser": [[], []]}
    origins = {kind: [[] for _ in lanes] for kind, lanes in notes.items()}

    def position(token, measure):
        if token.startswith("m"):
            match = re.fullmatch(r"m(\d+):(.+)", token)
            if not match:
                raise ValueError("Expected absolute position mN:BEAT")
            measure, token = int(match[1]), match[2]
        beat = _fraction(token)
        n, d = _sig_at(measure, sigs)
        if not 0 <= beat < n:
            raise ValueError(f"Beat must be within [0, {n}) in measure {measure}")
        return _rounded(_start(measure, sigs) + beat * Fraction(960, d))

    def add(kind, lane, note, line, col):
        start, end = _bounds(kind, note)
        for old, origin in zip(notes[kind][lane], origins[kind][lane]):
            a, b = _bounds(kind, old)
            if start == a or (start < b and a < end):
                error(line, col, f"Notes overlap on {kind} lane {lane} (line {origin})")
        notes[kind][lane].append(note)
        origins[kind][lane].append(line)

    def laser_value(token):
        parts = token.split(">")
        if len(parts) not in (1, 2):
            raise ValueError("Expected laser value V or V>VF")
        values = [_number(v) for v in parts]
        if any(not 0 <= v <= 1 for v in values):
            raise ValueError("Laser values must be in [0, 1]")
        return values[0] if len(values) == 1 else values

    def expand_copy(tokens, line):
        values = [t for t, _ in tokens]
        if (len(values) not in (4, 5) or values[2] != "->"
                or (len(values) == 5 and values[4] != "mirror")):
            raise ValueError("Expected copy SOURCE -> DEST [mirror]")
        source, dest = values[1], values[3]
        match = re.fullmatch(r"m(\d+)(?:-(\d+))?", source)
        if match:
            first = int(match[1])
            last = int(match[2]) if match[2] is not None else first
            if last < first:
                raise ValueError("Copy range must have positive length")
            start, end = _rounded(_start(first, sigs)), _rounded(_start(last + 1, sigs))
        else:
            match = re.fullmatch(r"(m\d+:.+)-(m\d+:.+)", source)
            if not match:
                raise ValueError("Expected copy range mN, mN-M or mN:BEAT-mM:BEAT")
            start, end = position(match[1], 0), position(match[2], 0)
        match = re.fullmatch(r"m(\d+)(?::(.+))?", dest)
        if not match:
            raise ValueError("Expected copy destination mN or mN:BEAT")
        destination = position(f"m{match[1]}:{match[2] or '0'}", 0)
        if end <= start:
            raise ValueError("Copy range must have positive length")
        # Compare the measure lengths encountered at corresponding offsets.
        offset = 0
        while offset < end - start:
            sm, _ = _locate(start + offset, sigs)
            dm, _ = _locate(destination + offset, sigs)
            sn, sd = _sig_at(sm, sigs)
            dn, dd = _sig_at(dm, sigs)
            if Fraction(sn, sd) != Fraction(dn, dd):
                raise ValueError("Copy source and destination have different measure lengths")
            offset += min(_start(sm + 1, sigs) - (start + offset),
                          _start(dm + 1, sigs) - (destination + offset))
        selected = [(kind, lane, copy.deepcopy(note)) for kind, lanes in notes.items()
                    for lane, items in enumerate(lanes) for note in items
                    if start <= _bounds(kind, note)[0] < end]
        shift = destination - start
        for y, *rest in [e for e in laser_events if start <= e[0] < end]:
            laser_events.append([y + shift, *rest])
        for y, lane, *rest in [e for e in fx_switches if start <= e[0] < end]:
            fx_switches.append([y + shift, 1 - lane if len(values) == 5 else lane, *rest])
        for kind, lane, note in selected:
            tag = fx_tags.get((lane, _bounds(kind, note)[0])) if kind == "fx" else None
            if isinstance(note, int):
                note += shift
            else:
                note[0] += shift
            if len(values) == 5:
                lane = (3 if kind == "bt" else 1) - lane
                if kind == "laser":
                    for point in note[1]:
                        v = point[1]
                        point[1] = [1 - x for x in v] if isinstance(v, list) else 1 - v
            add(kind, lane, note, line, tokens[0][1])
            if tag:
                fx_tags[(lane, _bounds(kind, note)[0])] = tag

    for line, measure, tokens in statements:
        try:
            first, col = tokens[0]
            values = [v for v, _ in tokens]
            if first == "copy":
                expand_copy(tokens, line)
                continue
            if first == "bpm":
                if len(tokens) != 3:
                    raise ValueError("Expected bpm BEAT VALUE")
                y, value = position(values[1], measure), _number(values[2])
                if value <= 0:
                    raise ValueError("BPM must be positive")
                bpms[y] = value
                continue
            y = position(first, measure)
            if len(tokens) == 3 and values[1] == "laser_effect":
                laser_events.append([y, values[2], line, tokens[2][1]])
                continue
            if len(tokens) >= 2 and values[1] == "fx_effect":
                if len(tokens) != 3 or not values[2].startswith(("L@", "R@")):
                    raise ValueError("Expected fx_effect L@NAME(...) or R@NAME(...)")
                lane_name, name, params = _tag(values[2])
                fx_switches.append([y, "LR".index(lane_name), name, params, line, tokens[2][1]])
                continue
            if len(tokens) < 2:
                raise ValueError("Expected button lanes or a laser section")
            if values[1] in {"l", "r", "l2", "r2"}:
                if len(tokens) < 3:
                    raise ValueError("Laser section needs an initial value")
                try:
                    initial = laser_value(values[2])
                except ValueError as exc:
                    error(line, tokens[2][1], exc)
                    initial = 0
                points = [[0, initial]]
                elapsed = Fraction()
                unit = Fraction(960, _sig_at(_locate(y, sigs)[0], sigs)[1])
                for token, point_col in tokens[3:]:
                    try:
                        match = re.fullmatch(r"\+([^:]+):(.+)", token)
                        if not match:
                            raise ValueError("Expected laser point +DT:V[>VF]")
                        dt = _fraction(match[1])
                        if dt <= 0:
                            raise ValueError("Laser DT must be positive; use V>VF for slams")
                        elapsed += dt * unit
                        ry = _rounded(elapsed)
                        if ry <= points[-1][0]:
                            raise ValueError("Laser points must advance by at least one pulse")
                        points.append([ry, laser_value(match[2])])
                    except ValueError as exc:
                        error(line, point_col, exc)
                section = [y, points]
                if values[1].endswith("2"):
                    section.append(2)
                add("laser", int(values[1][0] == "r"), section, line, tokens[1][1])
            else:
                for token, note_col in tokens[1:]:
                    try:
                        token, name, params = _tag(token)
                        parts = token.split("~")
                        if name is not None and parts[0] not in ("L", "R"):
                            raise ValueError("Only FX notes take @EFFECT / @KEY_SOUND")
                        if len(parts) not in (1, 2) or parts[0] not in _LANES:
                            raise ValueError(f"Invalid button note: {token!r}")
                        kind, lane = _LANES[parts[0]]
                        note = y
                        if len(parts) == 2:
                            if parts[1].startswith("m"):
                                length = position(parts[1], measure) - y
                            else:
                                unit = Fraction(960, _sig_at(_locate(y, sigs)[0], sigs)[1])
                                length = _rounded(_fraction(parts[1]) * unit)
                            if length <= 0:
                                raise ValueError("Long-note length must be positive")
                            note = [y, length]
                        add(kind, lane, note, line, note_col)
                        if name is not None:
                            fx_tags[(lane, y)] = (name, params, line, note_col)
                    except ValueError as exc:
                        error(line, note_col, exc)
        except ValueError as exc:
            error(line, tokens[0][1], exc)

    for kind, lanes in notes.items():
        for lane_idx, lane in enumerate(lanes):
            lane.sort(key=lambda n: _bounds(kind, n)[0])
            # Retain equivalent KSON shorthand choices when editing a base chart.
            old = (base or {}).get("note", {}).get(kind, [[] for _ in lanes])[lane_idx]
            by_start = {_bounds(kind, n)[0]: n for n in old}
            for i, note in enumerate(lane):
                original = by_start.get(_bounds(kind, note)[0])
                if original is not None and _note_key(kind, note) == _note_key(kind, original):
                    lane[i] = copy.deepcopy(_without_curves(original) if kind == "laser" else original)
    chart["note"] = notes
    _apply_effects(chart, notes, defs, fx_tags, fx_switches, laser_events, error)
    beat = chart.setdefault("beat", {})
    beat["bpm"], beat["time_sig"] = [[y, v] for y, v in sorted(bpms.items())], sigs
    if "disp_bpm" not in meta:
        values = list(bpms.values()) or [120]
        low, high = min(values), max(values)
        meta["disp_bpm"] = f"{low:g}" if low == high else f"{low:g}-{high:g}"
    if labels:
        comments = chart.setdefault("editor", {}).setdefault("comment", [])
        remaining = copy.deepcopy(comments)
        for m, label in labels:
            event = [_rounded(_start(m, sigs)), label]
            if event in remaining:
                remaining.remove(event)
            else:
                comments.append(event)
        comments.sort(key=lambda v: v[0])
    for issue in validate(chart):
        if issue.level == "error":
            error(0, 0, f"{issue.path}: {issue.message}")
    return chart, errors


def _apply_effects(chart, notes, defs, fx_tags, fx_switches, laser_events, error):
    """Write FX effects / key sounds and laser filter switches; the draft replaces the
    base chart's definitions and events (param_change and other keys are kept)."""
    audio = chart.get("audio", {})
    effect = audio.get("audio_effect", {})
    if not (defs["fx"] or defs["laser"] or fx_tags or fx_switches or laser_events or effect.get("fx", {}).get("long_event")
            or effect.get("laser", {}).get("pulse_event") or audio.get("key_sound", {}).get("fx")):
        return
    known = {"fx": _FX_EFFECTS | {"", *(d[0] for d in defs["fx"])}, "laser": _LASER_EFFECTS | {d[0] for d in defs["laser"]}}
    long_event, chip_event = {}, {}
    for y, lane, name, params, line, col in fx_switches:
        if not any(isinstance(n, list) and n[0] < y < n[0] + n[1] for n in notes["fx"][lane]):
            error(line, col, "fx_effect must fall inside a long FX note on that lane (after its start)")
        elif name not in known["fx"]:
            error(line, col, f"Unknown FX effect {name!r} (add: def fx {name} TYPE ...)")
        else:
            long_event.setdefault(name, [[], []])[lane].append([y, params] if params else y)
    for (lane, y), (name, params, line, col) in sorted(fx_tags.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        note = next(n for n in notes["fx"][lane] if _bounds("fx", n)[0] == y)
        if isinstance(note, list):
            if name not in known["fx"]:
                error(line, col, f"Unknown FX effect {name!r} (add: def fx {name} TYPE ...)")
                continue
            long_event.setdefault(name, [[], []])[lane].append([y, params] if params else y)
        else:
            if name not in _KEY_SOUNDS and "." not in name:
                error(line, col, f"Unknown FX key sound {name!r} (built-in: {', '.join(sorted(_KEY_SOUNDS))}, or a file name)")
                continue
            extra = set(params) - {"vol"}
            if extra:
                error(line, col, f"FX key sounds only take vol, not {', '.join(sorted(extra))}")
                continue
            try:
                event = [y, {"vol": _number(params["vol"])}] if params else y
            except ValueError as exc:
                error(line, col, exc)
                continue
            chip_event.setdefault(name, [[], []])[lane].append(event)
    for lanes in long_event.values():
        for events in lanes:
            events.sort(key=lambda e: e if isinstance(e, int) else e[0])
    pulse_event = {}
    for y, name, line, col in sorted(laser_events):
        if name not in known["laser"]:
            error(line, col, f"Unknown laser effect {name!r} (add: def laser {name} TYPE ...)")
            continue
        if y not in pulse_event.setdefault(name, []):
            pulse_event[name].append(y)
    audio = chart.setdefault("audio", {})
    effect = audio.setdefault("audio_effect", {})
    for kind, key, value in (("fx", "def", defs["fx"]), ("fx", "long_event", long_event),
                             ("laser", "def", defs["laser"]), ("laser", "pulse_event", pulse_event)):
        effect.setdefault(kind, {})[key] = value
        if not value:
            del effect[kind][key]
    audio.setdefault("key_sound", {}).setdefault("fx", {})["chip_event"] = chip_event
    for parent, key in ((effect, "fx"), (effect, "laser"), (audio["key_sound"], "fx"), (audio, "audio_effect"),
                        (audio, "key_sound")):
        child = parent.get(key)
        if isinstance(child, dict):
            if key == "fx" and parent is audio["key_sound"] and not child.get("chip_event"):
                child.pop("chip_event", None)
            if not child:
                del parent[key]


def _format_beat(value):
    value = Fraction(value)
    if value.denominator == 1:
        return str(value.numerator)
    if (value * 1000).denominator == 1:
        return f"{float(value):.3f}".rstrip("0").rstrip(".")
    whole, remainder = divmod(value.numerator, value.denominator)
    return f"{whole}+{remainder}/{value.denominator}" if whole else str(value)


def _format_laser(value):
    if isinstance(value, list):
        return ">".join(_format_laser(v) for v in value)
    return f"{value:.3f}".rstrip("0").rstrip(".")


def decompile(chart: dict) -> tuple[str, list[str]]:
    """Write a draft and identify chart data requiring a base for preservation."""
    warnings = []

    def warn(message):
        if message not in warnings:
            warnings.append(message)

    beat = chart["beat"]
    sigs = beat.get("time_sig") or [[0, [4, 4]]]
    measures = {}
    labels = {}

    def rows(measure):
        return measures.setdefault(measure, [])

    meta = chart["meta"]
    header = [f"{key}: {json.dumps(meta[field], ensure_ascii=False) if isinstance(meta[field], str) else meta[field]}"
              for key, field in _META.items() if field in meta]
    for key, field in _BGM.items():
        bgm = chart.get("audio", {}).get("bgm", {})
        if field not in bgm:
            continue
        value = bgm[field]
        if key == "preview":
            value = f"{value.get('offset', 0)} {value.get('duration', 15000)}"
        elif isinstance(value, str):
            value = json.dumps(value, ensure_ascii=False)
        header.append(f"{key}: {value}")
    initial_bpm = next((v for y, v in beat["bpm"] if y == 0), 120)
    initial_sig = _sig_at(0, sigs)
    header += [f"bpm: {initial_bpm}", f"time_sig: {initial_sig[0]}/{initial_sig[1]}"]
    for y, bpm in beat["bpm"]:
        if y:
            m, b = _locate(y, sigs)
            rows(m).append((b, 0, f"bpm {_format_beat(b)} {bpm}"))
    for m, (n, d) in sigs:
        if m:
            rows(m).append((Fraction(), -1, f"time_sig {n}/{d}"))
    audio = chart.get("audio", {})
    effect = audio.get("audio_effect", {})
    tags = {}   # (lane, y) -> "@name(...)"
    for name, lanes in effect.get("fx", {}).get("long_event", {}).items():
        for lane, events in enumerate(lanes):
            for event in events:
                y, params = (event, None) if isinstance(event, int) else (event[0], event[1])
                tags.setdefault((lane, y), []).append(_format_tag(name, params or {}))
    for name, lanes in audio.get("key_sound", {}).get("fx", {}).get("chip_event", {}).items():
        for lane, events in enumerate(lanes):
            for event in events:
                y, params = (event, None) if isinstance(event, int) else (event[0], event[1])
                params = {k: f"{v:g}" for k, v in (params or {}).items()}
                tags.setdefault((lane, y), []).append(_format_tag(name, params))
    fx_starts = {(lane, _bounds("fx", n)[0]) for lane, notes in enumerate(chart.get("note", {}).get("fx", [])) for n in notes}
    if any(len(v) > 1 for v in tags.values()):
        warn("several FX effects on one note")
    for lane, y in set(tags) - fx_starts:
        m, b = _locate(y, sigs)
        rows(m).append((b, 5, f"{_format_beat(b)} fx_effect {'LR'[lane]}{tags.pop((lane, y))[0]}"))
    defs = [f"def {kind} {name} {d['type']}" + "".join(f" {k}={v}" for k, v in d.get("v", {}).items())
            for kind in ("fx", "laser") for name, d in effect.get(kind, {}).get("def", [])]
    for name, ys in effect.get("laser", {}).get("pulse_event", {}).items():
        for y in ys:
            m, b = _locate(y, sigs)
            rows(m).append((b, 4, f"{_format_beat(b)} laser_effect {name}"))
    for kind in ("fx", "laser"):
        for key in effect.get(kind, {}).keys() - {"def", "long_event", "pulse_event"}:
            if effect[kind][key] or key != "param_change":
                warn(f"audio_effect.{kind}.{key}")
    if audio.get("key_sound", {}).get("laser"):
        warn("key_sound.laser")
    grouped = {}
    for name, (kind, lane) in _LANES.items():
        lanes = chart.get("note", {}).get(kind, [[] for _ in range(4 if kind == "bt" else 2)])
        for note in lanes[lane]:
            y, end = _bounds(kind, note)
            m, b = _locate(y, sigs)
            token = name
            if end > y:
                token += "~" + _format_beat(Fraction(end - y) / Fraction(960, _sig_at(m, sigs)[1]))
            if kind == "fx" and (lane, y) in tags:
                token += tags[(lane, y)][0]
            grouped.setdefault((m, b), []).append(token)
    for (m, b), tokens in grouped.items():
        rows(m).append((b, 1, f"{_format_beat(b)} {' '.join(tokens)}"))
    for lane, sections in enumerate(chart.get("note", {}).get("laser", [[], []])):
        for section in sections:
            y, points = section[:2]
            width = section[2] if len(section) > 2 else 1
            m, b = _locate(y, sigs)
            unit = Fraction(960, _sig_at(m, sigs)[1])
            tokens, previous = [], 0
            for ry, value, *curve in points:
                if curve:
                    warn("laser curves")
                prefix = f"+{_format_beat(Fraction(ry - previous) / unit)}:" if tokens else ""
                tokens.append(prefix + _format_laser(value))
                previous = ry
            name = "lr"[lane] + ("2" if width == 2 else "")
            rows(m).append((b, lane + 2, f"{_format_beat(b)} {name} {' '.join(tokens)}"))
    for y, label in chart.get("editor", {}).get("comment", []):
        m, b = _locate(y, sigs)
        if b:
            warn("editor comments away from measure starts")
        else:
            if m in labels:
                warn("multiple editor comments at one measure start")
            labels.setdefault(m, []).append(label)
            rows(m)
    for key in ("scroll_speed", "stop"):
        if beat.get(key):
            warn(key)
    for key in ("camera", "bg"):
        if chart.get(key):
            warn(key)
    # Also report less common metadata/provenance not covered by the DSL.
    for path, obj, supported in (
        ("meta", meta, set(_META.values())),
        ("beat", beat, {"bpm", "time_sig", "scroll_speed", "stop"}),
        ("note", chart.get("note", {}), {"bt", "fx", "laser"}),
        ("audio", audio, {"bgm", "audio_effect", "key_sound"}),
        ("audio.bgm", audio.get("bgm", {}), set(_BGM.values())),
        ("editor", chart.get("editor", {}), {"comment"}),
        ("", chart, {"format_version", "meta", "beat", "note", "audio", "camera", "bg", "editor"}),
    ):
        for key in obj.keys() - supported:
            warn(f"{path + '.' if path else ''}{key}")
    output = [f"# unsupported: {warning}" for warning in warnings]
    output += header + defs
    for m, content in sorted(measures.items()):
        output.append("")
        names = labels.get(m, [])
        if names:
            output.append(f"@m{m} {json.dumps(names[0], ensure_ascii=False)}")
        else:
            output.append(f"@m{m}")
        output.extend(line for _, _, line in sorted(content, key=lambda row: row[:2]))
    return "\n".join(output) + "\n", warnings
