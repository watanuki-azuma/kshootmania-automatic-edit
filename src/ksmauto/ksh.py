"""Import KSH charts into plain KSON dictionaries."""

import math
import re
from pathlib import Path


_EFFECT_TYPES = dict(zip(
    ("Retrigger", "Gate", "Flanger", "PitchShift", "BitCrusher", "Phaser",
     "Wobble", "TapeStop", "Echo", "SideChain", "SwitchAudio", "HighPassFilter",
     "LowPassFilter", "PeakingFilter"),
    ("retrigger", "gate", "flanger", "pitch_shift", "bitcrusher", "phaser",
     "wobble", "tapestop", "echo", "sidechain", "switch_audio", "high_pass_filter",
     "low_pass_filter", "peaking_filter"),
))
_FX_NAMES = {k: v for k, v in list(_EFFECT_TYPES.items())[:10]}
_FILTER_NAMES = {"peak": "peaking_filter", "hpf1": "high_pass_filter",
                 "lpf1": "low_pass_filter", "bitc": "bitcrusher",
                 "fx": "fx", "fx;bitc": "fx;bitcrusher"}
_PARAM_NAMES = {
    "attackTime": "attack_time", "bandwidth": "bandwidth", "chunkSize": "chunk_size",
    "delay": "delay", "depth": "depth", "feedback": "feedback",
    "feedbackLevel": "feedback_level", "fileName": "filename", "freq": "freq",
    "freqMax": "freq_max", "gain": "gain", "hiCutGain": "hi_cut_gain",
    "hiFreq": "freq_2", "holdTime": "hold_time", "loFreq": "freq_1", "mix": "mix",
    "overWrap": "overlap", "period": "period", "pitch": "pitch", "Q": "q",
    "rate": "rate", "ratio": "ratio", "reduction": "reduction",
    "releaseTime": "release_time", "speed": "speed", "stage": "stage",
    "stereoWidth": "stereo_width", "trigger": "trigger", "updateTrigger": "update_trigger",
    "v": "v", "volume": "vol", "waveLength": "wave_length", "updatePeriod": "update_period",
}
_LEGACY_FX = dict(zip("SVTWUGHKILJFPBQXAD", (
    "Retrigger;8", "Retrigger;12", "Retrigger;16", "Retrigger;24", "Retrigger;32",
    "Gate;4", "Gate;8", "Gate;12", "Gate;16", "Gate;24", "Gate;32", "Flanger",
    "PitchShift;12", "BitCrusher;5", "Phaser", "Wobble;12", "TapeStop", "SideChain")))
_TILTS = {"normal", "bigger", "biggest", "keep_normal", "keep_bigger", "keep_biggest", "zero"}


def _number(text, default=0, *, integer=True):
    pattern = r"\s*[+-]?\d+" if integer else r"\s*[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
    match = re.match(pattern, text)
    if not match:
        return default
    value = int(match[0]) if integer else float(match[0])
    return value if integer or math.isfinite(value) else default


def _round(value):
    return math.copysign(math.floor(abs(value) * 1000 + 0.5) / 1000, value)


def _put(events, y, value, *, graph=False):
    if graph and y in events:
        previous = events[y][0] if isinstance(events[y], list) else events[y]
        events[y] = [previous, value]
    else:
        events[y] = value


def _pairs(events):
    return [[y, v] for y, v in sorted(events.items())]


def _time_sig(value):
    parts = value.split("/", 1)
    if len(parts) != 2 or any(_number(p) <= 0 for p in parts):
        raise ValueError(f"Invalid KSH time signature: {value!r}")
    return [_number(p) for p in parts]


def load_ksh(path) -> dict:
    """Read UTF-8 (with or without BOM), falling back to Windows Shift_JIS."""
    data = Path(path).read_bytes()
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp932")
    return parse_ksh(text)


def parse_ksh(text: str) -> dict:
    """Convert KSH using libkson's version-dependent import conventions."""
    lines = [line.removesuffix("\r") for line in text.removeprefix("\ufeff").split("\n")]
    try:
        header_end = lines.index("--")
    except ValueError:
        raise ValueError("KSH header must end with '--'") from None
    header = {}
    comments, unknown_lines = [], []
    for line in lines[:header_end]:
        if line.startswith("//"):
            comments.append([0, line[2:].replace("\\n", "\n")])
        elif "=" in line and not line.startswith("="):
            key, value = line.split("=", 1)
            header[key] = value
        else:
            unknown_lines.append([0, line])
    if "title" not in header:
        raise ValueError("KSH requires a title header")
    pop = header.pop
    version = pop("ver", "100")
    version = pop("ver_compat", "") or version
    ver = _number(version, 100)
    meta = {"title": pop("title"), "artist": pop("artist", ""),
            "chart_author": pop("effect", ""), "level": max(1, min(20, _number(pop("level", "1"))))}
    for ksh, kson in (("title_translit", "title_translit"), ("title_img", "title_img_filename"),
                      ("artist_translit", "artist_translit"), ("artist_img", "artist_img_filename"),
                      ("jacket", "jacket_filename"), ("illustrator", "jacket_author"),
                      ("icon", "icon_filename"), ("information", "information")):
        value = pop(ksh, "")
        if value:
            meta[kson] = value
    difficulty = pop("difficulty", "infinite")
    meta["difficulty"] = {"light": 0, "challenge": 1, "extended": 2, "infinite": 3}.get(difficulty, difficulty)
    meta["disp_bpm"] = pop("t", "")
    std_bpm = _number(pop("to", "0"), integer=False)
    if std_bpm:
        meta["std_bpm"] = std_bpm
    bpm, stops, scroll = {}, {}, {}

    def insert_bpm(y, value):
        if "-" not in value:
            v = _round(_number(value, integer=False))
            bpm[y] = min(v, 65535) if ver >= 130 else v

    if meta["disp_bpm"]:
        insert_bpm(0, meta["disp_bpm"])
    sig = _time_sig(pop("beat", "4/4"))
    signatures = {0: sig}
    music = pop("m", "").split(";")[:4]
    bgm = {"filename": music[0], "vol": _number(pop("mvol", "100") or "100") / 100 * (0.6 if ver == 100 else 1),
           "offset": _number(pop("o", "0")),
           "preview": {"offset": _number(pop("po", "0")), "duration": _number(pop("plength", "0"))}}
    if len(music) > 1:
        bgm["legacy"] = {"fp_filenames": music[1:]}
    effects = {kind: {"def": [], "param_change": {}} for kind in ("fx", "laser")}
    effects["fx"]["long_event"] = {}
    effects["laser"].update(pulse_event={}, peaking_filter_delay=_number(pop("pfilterdelay", "40") or "40"))
    gain = {0: _number(pop("pfiltergain"), 50) / 100} if "pfiltergain" in header else {}
    slam_vol = {0: _number(pop("chokkakuvol", "50") or "50") / 100}
    key_laser = {"legacy": {"vol_auto": _number(pop("chokkakuautovol", "1") or "1") != 0}, "slam_event": {}}
    key_fx = {}

    def filtertype(y, value):
        name = _FILTER_NAMES.get(value, value)
        defs = effects["laser"]["def"]
        if name in ("fx", "fx;bitcrusher") and not any(d[0] == name for d in defs):
            if name == "fx":
                if len(music) < 2 or not music[1]:
                    return
                definition = {"type": "switch_audio", "v": {"filename": music[1]}}
            else:
                definition = {"type": "bitcrusher"}
            defs.append([name, definition])
        events = effects["laser"]["pulse_event"].setdefault(name, [])
        if y not in events:
            events.append(y)

    if "filtertype" in header:
        filtertype(0, pop("filtertype"))
    backgrounds = pop("bg", "desert").split(";")[:2]
    if len(backgrounds) == 2 and backgrounds[0] == backgrounds[1]:
        backgrounds.pop()
    layer = pop("layer", "arrow").split(";" if ver >= 166 else "/")
    flags = _number(layer[2], 3) if len(layer) > 2 else 3
    bg = {"legacy": {"bg": [{"filename": s} for s in backgrounds],
                     "layer": {"filename": layer[0], "duration": _number(layer[1]) if len(layer) > 1 else 0,
                               "rotation": {"tilt": bool(flags & 1), "spin": bool(flags & 2)}}}}
    movie, movie_offset = pop("v", ""), _number(pop("vo", "0"))
    if movie or movie_offset:
        bg["legacy"]["movie"] = {"filename": movie, "offset": movie_offset}
    total = _number(pop("total", "0"))
    unknown = {"meta": header, "option": {}, "line": unknown_lines}
    notes = {"bt": [[] for _ in range(4)], "fx": [[], []], "laser": [[], []]}
    active = {"bt": [None] * 4, "fx": [None] * 2, "laser": [None] * 2}
    body, tilts, patterns, curves = {}, {}, {}, {}
    legacy_tilt = False

    def flush_button(kind, lane):
        state = active[kind][lane]
        if state is not None:
            notes[kind][lane].append([state["y"], int(state["length"])])
            active[kind][lane] = None

    def flush_laser(lane):
        state = active["laser"][lane]
        active["laser"][lane] = None
        if state is None or len(state["points"]) < 2:
            return
        points, converted = state["points"], []
        i = 0
        while i < len(points):
            ry, v = points[i]
            if i + 1 < len(points) and points[i + 1][0] - ry <= 30 and points[i + 1][1] != v:
                converted.append([ry, [v, points[i + 1][1]]])
                if (i + 2 == len(points) or points[i + 2][0] - points[i + 1][0] > 30
                        or points[i + 2][1] == points[i + 1][1]):
                    i += 1
            else:
                converted.append([ry, v])
            i += 1
        section = [state["y"], converted]
        if state["wide"]:
            section.append(2)
        notes["laser"][lane].append(section)

    def fx_event(lane, y, effect, param):
        fields = effect.split(";")
        name = _FX_NAMES.get(fields[0], fields[0])
        p1 = _number(param) if param else (_number(fields[1]) if len(fields) > 1 else None)
        p2 = _number(fields[2]) if len(fields) > 2 else None
        events = effects["fx"]["long_event"].setdefault(name, [[], []])
        events[lane].append([y, [p1, p2]])

    chart_lines, options, annotations = [], [], []
    pulse, measure = 0, 0
    for line in lines[header_end + 1:]:
        if not line:
            continue
        if line.startswith("//"):
            annotations.append((len(chart_lines), True, line[2:].replace("\\n", "\n")))
        elif line.startswith("#"):
            match = re.fullmatch(r"#define_(fx|filter) +([^ ]+) +(.*?) *", line)
            if not match:
                continue
            kind, name, params_text = match.groups()
            kind = "fx" if kind == "fx" else "laser"
            params = {}
            for field in params_text.split(";"):
                if "=" in field:
                    k, v = field.split("=", 1)
                    if v:
                        params.setdefault(k, v)
            effect_type = _EFFECT_TYPES.get(params.pop("type", ""))
            if effect_type is None:
                continue
            name = (_FX_NAMES if kind == "fx" else _FILTER_NAMES).get(name, name)
            definition = {"type": effect_type, "v": {_PARAM_NAMES[k]: v for k, v in params.items() if k in _PARAM_NAMES}}
            defs = effects[kind]["def"]
            existing = next((d for d in defs if d[0] == name), None)
            if existing is None:
                defs.append([name, definition])
            else:
                existing[1] = definition
        elif "|" in line:
            chart_lines.append(line)
        elif "=" in line and not line.startswith("="):
            k, v = line.split("=", 1)
            if k == "beat":
                sig = _time_sig(v)
                signatures[measure] = sig
            else:
                options.append((len(chart_lines), k, v))
        elif line != "--":
            annotations.append((len(chart_lines), False, line))
        else:
            length = 960 * sig[0] // sig[1]
            if chart_lines:
                step = length / len(chart_lines)
                local = {}
                for idx, k, v in options:
                    y = pulse + int(idx * step)
                    if k.endswith("_curve"):
                        if ";" in v:
                            curves.setdefault(k[:-6], {})[y] = [_number(p, integer=False) for p in v.split(";", 1)]
                    elif k == "t":
                        insert_bpm(y if bpm else 0, v)
                    elif k == "stop":
                        if _number(v) > 0:
                            stops[y] = _number(v) * 5
                    elif k in ("zoom_top", "zoom_bottom", "zoom_side", "center_split", "rotation_deg", "scroll_speed"):
                        limit = 300 if ver < 167 and k.startswith("zoom_") else 65535
                        value = _number(v[:4] if ver < 167 and k.startswith("zoom_") else v,
                                        integer=k not in ("rotation_deg", "scroll_speed"))
                        graph = scroll if k == "scroll_speed" else body.setdefault(k, {})
                        if k == "scroll_speed" or abs(value) <= limit or (ver < 167 and k.startswith("zoom_") and y in graph):
                            _put(graph, y, value, graph=True)
                    elif k == "tilt":
                        if re.match(r"[\d-]", v):
                            value = _round(_number(v, integer=False))
                            if ver < 170 and abs(value) >= 10:
                                legacy_tilt = True
                            if abs(value) > 1000:
                                continue
                        else:
                            value = {"big": "bigger", "keep": "keep_bigger"}.get(v, v)
                            value = value if value in _TILTS else "normal"
                        _put(tilts, y, value, graph=y in tilts and not isinstance(tilts[y], str))
                    elif k == "chokkakuvol":
                        slam_vol[y] = _number(v) / 100
                    elif k == "pfiltergain":
                        gain.setdefault(y, _number(v, 50) / 100)
                    elif k == "filtertype":
                        filtertype(y, v)
                    elif k in ("fx-l", "fx-r", "fx-l_param1", "fx-r_param1", "fx-l_se", "fx-r_se",
                               "laserrange_l", "laserrange_r", "chokkakuse"):
                        local[idx, k] = v
                    elif k.startswith(("fx:", "filter:")):
                        fields = k.split(":")
                        if len(fields) >= 3 and fields[1] and fields[2] in _PARAM_NAMES:
                            kind = "fx" if fields[0] == "fx" else "laser"
                            name = (_FX_NAMES if kind == "fx" else _FILTER_NAMES).get(fields[1], fields[1])
                            changes = effects[kind]["param_change"].setdefault(name, {}).setdefault(_PARAM_NAMES[fields[2]], {})
                            changes[y] = v
                    else:
                        unknown["option"].setdefault(k, []).append([y, v])
                for idx, line in enumerate(chart_lines):
                    y = pulse + int(idx * step)
                    blocks = line.split("|")
                    for kind, block, count in (("bt", blocks[0], 4), ("fx", blocks[1], 2)):
                        for lane, char in enumerate(block[:count]):
                            state = active[kind][lane]
                            chip, long = ("1", "2") if kind == "bt" else ("2", "1")
                            if char == chip:
                                if kind == "bt":
                                    flush_button(kind, lane)
                                notes[kind][lane].append(y)
                                if kind == "fx":
                                    sound = local.get((idx, "fx-l_se" if lane == 0 else "fx-r_se"))
                                    if sound is not None:
                                        fields = sound.split(";")
                                        vol = _number(fields[1], 100) / 100 if len(fields) > 1 else 1
                                        key_fx.setdefault(fields[0], [[], []])[lane].append([y, {"vol": vol}])
                            elif char == long or (kind == "fx" and char != "0"):
                                if state is None:
                                    state = {"y": y, "length": 0, "effect": None, "param": "", "legacy": False}
                                    active[kind][lane] = state
                                state["length"] += step
                                if kind == "fx":
                                    key = "fx-l" if lane == 0 else "fx-r"
                                    param = local.get((idx, key + "_param1"), state["param"] if char != "1" else "")
                                    effect = local.get((idx, key)) if char == "1" else _LEGACY_FX.get(char, "")
                                    if char == "1" and effect is None and state["legacy"]:
                                        effect, param = "", ""
                                    if effect is not None:
                                        if char == "1" or (effect, param) != (state["effect"], state["param"]):
                                            fx_event(lane, y, effect, param)
                                        state.update(effect=effect, param=param, legacy=char != "1")
                            else:
                                flush_button(kind, lane)
                    laser_block = blocks[2] if len(blocks) > 2 else ""
                    for lane, char in enumerate(laser_block[:2]):
                        if char == "-":
                            flush_laser(lane)
                        elif char != ":":
                            state = active["laser"][lane]
                            if state is None:
                                state = {"y": y, "wide": local.get((idx, "laserrange_l" if lane == 0 else "laserrange_r")) == "2x", "points": []}
                                active["laser"][lane] = state
                            x = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmno".find(char)
                            value = max(x, 0) / 50
                            if state["wide"] and char in "Cb":
                                value = 0.25 if char == "C" else 0.75
                            state["points"].append([y - state["y"], value])
                            sound = local.get((idx, "chokkakuse"))
                            if sound:
                                events = key_laser["slam_event"].setdefault(sound, [])
                                if y not in events:
                                    events.append(y)
                    spin = re.match(r"([@S])([()<>])(.+)", laser_block[2:])
                    if spin:
                        marker, direction, params = spin.groups()
                        if marker == "S" and direction not in "<>":
                            continue
                        fields = params.split(";")
                        name = "swing" if marker == "S" else ("spin" if direction in "()" else "half_spin")
                        event = [y, -1 if direction in "(<" else 1, _number(fields[0]) * 5]
                        if name == "swing":
                            defaults = ["192", "250", "3", "2"]
                            defaults[:len(fields[:4])] = fields[:4]
                            event.append(dict(zip(("scale", "repeat", "decay_order"), map(_number, defaults[1:]))))
                        patterns.setdefault(name, []).append(event)
                for idx, comment, value in annotations:
                    (comments if comment else unknown_lines).append([pulse + int(idx * step), value])
            chart_lines, options, annotations = [], [], []
            pulse += length
            measure += 1

    for lane in range(2):
        flush_laser(lane)
    # Notes may be published after later chips; libkson stores them by pulse.
    for kind in ("bt", "fx"):
        for lane in notes[kind]:
            by_pulse = {}
            for note in lane:
                y = note[0] if isinstance(note, list) else note
                by_pulse.setdefault(y, note)
            lane[:] = [note for _, note in sorted(by_pulse.items())]
    for name, lanes in effects["fx"]["long_event"].items():
        effect_type = next((d[1]["type"] for d in effects["fx"]["def"] if d[0] == name), name)
        for lane in lanes:
            for event in lane:
                p1, p2 = event[1]
                if p1 is None or p1 == -99999:
                    p1 = {"retrigger": 8, "gate": 4, "wobble": 12, "pitch_shift": 12,
                          "bitcrusher": 5, "tapestop": 50, "echo": 4}.get(effect_type, 0)
                if p2 is None or p2 == -99999:
                    p2 = 60 if effect_type == "echo" else 0
                params = {}
                if effect_type in ("retrigger", "gate", "wobble", "echo") and p1 > 0:
                    params["wave_length"] = f"1/{p1}"
                if effect_type in ("pitch_shift", "bitcrusher", "tapestop", "echo"):
                    key, value = {"pitch_shift": ("pitch", str(p1)), "bitcrusher": ("reduction", f"{p1}samples"),
                                  "tapestop": ("speed", f"{p1}%"), "echo": ("feedback_level", f"{p2}%")}[effect_type]
                    params[key] = value
                event[1] = params
    if legacy_tilt:
        for y, value in tilts.items():
            if isinstance(value, (int, float)):
                tilts[y] = _round(value * 1.4)
            elif isinstance(value, list):
                tilts[y] = [_round(v * 1.4) if isinstance(v, (int, float)) else v for v in value]
    tilts.setdefault(0, "normal")
    scroll.setdefault(0, 1.0)
    gain.setdefault(0, 0.5)

    def graph_points(name, graph):
        result = _pairs(graph)
        for point in result:
            if point[0] in curves.get(name, {}):
                point.append(curves[name][point[0]])
        return result

    for lane_idx, lane in enumerate(notes["laser"]):
        for y, points, *width in lane:
            for point in points:
                curve = curves.get("laser_l" if lane_idx == 0 else "laser_r", {}).get(y + point[0])
                if curve is not None:
                    point.append(curve)
    tilt_events = _pairs(tilts)
    for event in tilt_events:
        curve = curves.get("tilt", {}).get(event[0])
        if curve is not None and not isinstance(event[1], str):
            event[1] = [event[1], curve]
    for effect in effects.values():
        for changes in effect["param_change"].values():
            for param, events in changes.items():
                changes[param] = _pairs(events)
    effects["laser"]["legacy"] = {"filter_gain": _pairs(gain)}
    key_laser["vol"] = _pairs(slam_vol)
    chart = {"format_version": 1, "meta": meta,
             "beat": {"bpm": _pairs(bpm), "time_sig": _pairs(signatures),
                      "scroll_speed": graph_points("scroll_speed", scroll), "stop": _pairs(stops)},
             "gauge": {"total": total}, "note": notes,
             "audio": {"bgm": bgm, "key_sound": {"fx": {"chip_event": key_fx}, "laser": key_laser}, "audio_effect": effects},
             "camera": {"tilt": tilt_events, "cam": {"body": {k: graph_points(k, v) for k, v in body.items()},
                                                      "pattern": {"laser": {"slam_event": patterns}}}},
             "bg": bg, "compat": {"ksh_unknown": unknown}}
    if ver < 200:
        chart["compat"]["ksh_version"] = version
    if comments:
        chart["editor"] = {"comment": sorted(comments, key=lambda p: p[0])}
    return chart
