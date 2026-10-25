"""KSON JSON I/O, semantic defaults, and structural validation."""

import copy
import json
import math
from dataclasses import dataclass
from pathlib import Path


_EFFECT_DEFAULTS = {
    "retrigger": {"update_period": "1/2", "wave_length": "0", "rate": "70%", "update_trigger": "off", "mix": "0%>100%"},
    "gate": {"wave_length": "0", "rate": "50%", "mix": "0%>90%"},
    "flanger": {"period": "2.0", "delay": "30samples", "depth": "45samples", "feedback": "60%",
                "stereo_width": "0%", "vol": "75%", "mix": "0%>80%"},
    "pitch_shift": {"pitch": "0>12", "chunk_size": "700samples", "overlap": "40%", "mix": "0%>100%"},
    "bitcrusher": {"reduction": "0samples-30samples", "mix": "0%>100%"},
    "phaser": {"period": "1/2", "stage": "6", "freq_1": "1500Hz", "freq_2": "20000Hz", "q": "0.707",
               "feedback": "35%", "stereo_width": "75%", "hi_cut_gain": "-8.0dB", "mix": "0%>50%"},
    "wobble": {"wave_length": "0", "freq_1": "500Hz", "freq_2": "20000Hz", "q": "1.414", "mix": "0%>80%"},
    "tapestop": {"speed": "50%", "trigger": "off>on", "mix": "0%>100%"},
    "echo": {"update_period": "0", "wave_length": "0", "update_trigger": "off>on", "feedback_level": "60%", "mix": "0%>100%"},
    "sidechain": {"period": "1/4", "hold_time": "50ms", "attack_time": "10ms", "release_time": "1/8", "ratio": "1.0>5.0"},
    "peaking_filter": {"v": "0%-100%", "gain": "50%", "mix": "0%>100%"},
    "high_pass_filter": {"v": "0%-100%", "mix": "0%>100%"},
    "low_pass_filter": {"v": "0%-100%", "mix": "0%>100%"},
}


@dataclass(frozen=True)
class Issue:
    level: str
    path: str
    message: str


def load_kson(path) -> dict:
    """Read a UTF-8 KSON file without changing its JSON representation."""
    with Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def dumps_kson(chart) -> str:
    """Serialize UTF-8-friendly JSON with a final LF and no non-JSON numbers."""
    return json.dumps(chart, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n"


def save_kson(chart, path):
    Path(path).write_text(dumps_kson(chart), encoding="utf-8", newline="\n")


def normalize(chart) -> dict:
    """Return a copy with spec defaults and shorthand arrays made explicit.

    Empty optional containers are equivalent to omission. Defaults for event
    streams also apply before their first event. No required metadata is invented.
    """
    result = copy.deepcopy(chart)

    def clean(value, *, root=False):
        if isinstance(value, dict):
            for k in list(value):
                if root and k == "impl":
                    continue
                clean(value[k])
                if value[k] == {} or value[k] == []:
                    del value[k]
        elif isinstance(value, list):
            for item in value:
                clean(item)

    clean(result, root=True)

    def defaults(path, fields):
        obj = result
        for key in path.split("."):
            obj = obj.setdefault(key, {})
        for key, value in fields.items():
            obj.setdefault(key, copy.deepcopy(value))
        return obj

    beat = defaults("beat", {"time_sig": [[0, [4, 4]]], "scroll_speed": [[0, 1.0]]})
    defaults("gauge", {"total": 0})
    defaults("audio.bgm", {"vol": 1.0, "offset": 0})
    defaults("audio.bgm.preview", {"offset": 0, "duration": 15000})
    laser_sound = defaults("audio.key_sound.laser", {"vol": [[0, 0.5]]})
    defaults("audio.key_sound.laser.legacy", {"vol_auto": False})
    defaults("audio.audio_effect.laser", {"peaking_filter_delay": 0})
    laser_legacy = defaults("audio.audio_effect.laser.legacy", {"filter_gain": [[0, 0.5]]})
    camera = defaults("camera", {"tilt": [[0, "normal"]]})
    defaults("bg.legacy.layer", {"duration": 0})
    defaults("bg.legacy.layer.rotation", {"tilt": True, "spin": True})
    defaults("bg.legacy.movie", {"offset": 0})
    for events, value in ((beat["time_sig"], [4, 4]), (beat["scroll_speed"], 1.0),
                          (laser_sound["vol"], 0.5), (laser_legacy["filter_gain"], 0.5),
                          (camera["tilt"], "normal")):
        if events and events[0][0] != 0:
            events.insert(0, [0, value])

    def graph(points):
        for point in points:
            if not isinstance(point[1], list):
                point[1] = [point[1], point[1]]
            if len(point) == 2:
                point.append([0.0, 0.0])

    graph(beat["scroll_speed"])
    notes = result.setdefault("note", {})
    for kind, count in (("bt", 4), ("fx", 2), ("laser", 2)):
        lanes = notes.setdefault(kind, [[] for _ in range(count)])
        for lane in lanes:
            if kind != "laser":
                lane[:] = [[n, 0] if isinstance(n, int) else n for n in lane]
            else:
                for section in lane:
                    if len(section) == 2:
                        section.append(1)
                    graph(section[1])
    for points in camera.get("cam", {}).get("body", {}).values():
        graph(points)
    for event in camera["tilt"]:
        value = event[1]
        if isinstance(value, str):
            continue
        curve = [0.0, 0.0]
        if isinstance(value, list) and isinstance(value[1], list):
            value, curve = value
        if not isinstance(value, list):
            value = [value, value]
        event[1] = [value, curve]
    for lanes in result.get("audio", {}).get("key_sound", {}).get("fx", {}).get("chip_event", {}).values():
        for lane in lanes:
            lane[:] = [[n, {"vol": 1.0}] if isinstance(n, int) else n for n in lane]
            for event in lane:
                event[1].setdefault("vol", 1.0)
    for lanes in result.get("audio", {}).get("audio_effect", {}).get("fx", {}).get("long_event", {}).values():
        for lane in lanes:
            lane[:] = [[n, {}] if isinstance(n, int) else n for n in lane]
    version = result.get("compat", {}).get("ksh_version", "200")
    legacy_version = version.isdecimal() and int(version) < 200
    for kind in ("fx", "laser"):
        for name, definition in result["audio"]["audio_effect"].get(kind, {}).get("def", []):
            params = definition.setdefault("v", {})
            for key, value in _EFFECT_DEFAULTS.get(definition["type"], {}).items():
                if definition["type"] == "sidechain" and key == "release_time" and legacy_version:
                    value = "1/16"
                params.setdefault(key, value)
    patterns = camera.get("cam", {}).get("pattern", {}).get("laser", {}).get("slam_event", {})
    for event in patterns.get("swing", []):
        if len(event) == 3:
            event.append({})
        for key, value in (("scale", 250.0), ("repeat", 3), ("decay_order", 2)):
            event[3].setdefault(key, value)
    # A single legacy background is used for both gauge ranges.
    backgrounds = result["bg"]["legacy"].get("bg", [])
    if len(backgrounds) == 1:
        backgrounds.append(copy.deepcopy(backgrounds[0]))
    return result


# Schema descriptors mirror the spec's dictionaries, arrays, and unions.
_GRAPH = ("tuple", "uint", ("union", "number", ("tuple", "number", "number")),
          ("optional", ("tuple", "unit", "unit")))
_BUTTON = ("union", "uint", ("tuple", "uint", "uint"))
_LASER = ("tuple", "uint", ("events", _GRAPH, "relative"), ("optional", "width"))
_DEF = ("tuple", "string", {"type": "string", "v?": ("dict", "string")})
_PARAM_CHANGE = ("dict", ("dict", ("events", ("tuple", "uint", "string"))))
_FX_EVENT = ("dict", ("array", ("events", ("union", "uint", ("tuple", "uint", ("dict", "string")))), 2, 2))
_SCHEMA = {
    "format_version": "version",
    "meta": {"title": "string", "artist": "string", "chart_author": "string",
             "difficulty": "difficulty", "level": "level", "disp_bpm": "string",
             **{k + "?": "string" for k in ("title_translit", "title_img_filename", "artist_translit",
                 "artist_img_filename", "jacket_filename", "jacket_author", "icon_filename", "information")},
             "std_bpm?": "positive"},
    "beat": {"bpm": ("events", ("tuple", "uint", "positive"), "nonempty"),
             "time_sig?": ("events", ("tuple", "uint", ("tuple", "positive_int", "positive_int"))),
             "scroll_speed?": ("events", _GRAPH), "stop?": ("events", ("tuple", "uint", "uint"))},
    "gauge?": {"total?": "uint"},
    "note?": {"bt?": ("array", ("events", _BUTTON), 4, 4),
              "fx?": ("array", ("events", _BUTTON), 2, 2),
              "laser?": ("array", ("events", _LASER), 2, 2)},
    "audio?": {
        "bgm?": {"filename?": "string", "vol?": "number", "offset?": "int",
                 "preview?": {"offset?": "uint", "duration?": "uint"},
                 "legacy?": {"fp_filenames": ("array", "string", 0, None)}},
        "key_sound?": {
            "fx?": {"chip_event": ("dict", ("array", ("events", ("union", "uint", ("tuple", "uint", {"vol?": "number"}))), 2, 2))},
            "laser?": {"vol?": ("events", ("tuple", "uint", "number")),
                       "slam_event?": ("dict", ("events", "uint")), "legacy?": {"vol_auto?": "bool"}}},
        "audio_effect?": {
            "fx?": {"def?": ("array", _DEF, 0, None), "param_change?": _PARAM_CHANGE, "long_event?": _FX_EVENT},
            "laser?": {"def?": ("array", _DEF, 0, None), "param_change?": _PARAM_CHANGE,
                       "pulse_event?": ("dict", ("events", "uint")), "peaking_filter_delay?": "uint",
                       "legacy?": {"filter_gain?": ("events", ("tuple", "uint", "number"))}}}},
    "camera?": {"tilt?": ("events", ("tuple", "uint", "tilt")),
                "cam?": {"body?": {k + "?": ("events", _GRAPH) for k in
                                     ("zoom_top", "zoom_bottom", "zoom_side", "rotation_deg", "center_split")},
                         "pattern?": {"laser?": {"slam_event?": {
                             "spin?": ("events", ("tuple", "uint", "direction", "uint")),
                             "half_spin?": ("events", ("tuple", "uint", "direction", "uint")),
                             "swing?": ("events", ("tuple", "uint", "direction", "uint", ("optional", {
                                 "scale?": "number", "repeat?": "uint", "decay_order?": "decay"})))}}}}},
    "bg?": {"filename?": "string", "legacy?": {
        "bg?": ("array", {"filename?": "string"}, 1, 2),
        "layer?": {"filename?": "string", "duration?": "int", "rotation?": {"tilt?": "bool", "spin?": "bool"}},
        "movie?": {"filename?": "string", "offset?": "int"}}},
    "editor?": {"app_name?": "string", "app_version?": "string", "comment?": ("events", ("tuple", "uint", "string"))},
    "compat?": {"ksh_version?": "string", "ksh_unknown?": {
        "meta?": ("dict", "string"), "option?": ("dict", ("events", ("tuple", "uint", "string"))),
        "line?": ("events", ("tuple", "uint", "string"))}},
    "impl?": ("dict", "any"),
}


def validate(chart) -> list[Issue]:
    """Report structural errors, invalid ranges, ordering, and lane overlaps."""
    issues = []

    def error(path, message):
        issues.append(Issue("error", path, message))

    def number(v):
        return type(v) is int or (type(v) is float and math.isfinite(v))

    def uint(v):
        return type(v) is int and v >= 0

    def primitive(v, kind):
        if kind == "any":
            return True
        if kind == "string":
            return isinstance(v, str)
        if kind == "bool":
            return type(v) is bool
        if kind == "int":
            return type(v) is int
        if kind == "uint":
            return uint(v)
        if kind == "number":
            return number(v)
        if kind == "positive":
            return number(v) and v > 0
        if kind == "positive_int":
            return uint(v) and v > 0
        if kind == "unit":
            return number(v) and 0 <= v <= 1
        if kind == "difficulty":
            return isinstance(v, str) or (uint(v) and v <= 3)
        if kind == "level":
            return number(v) and 1 <= v < 21  # sdvx.in levels go up to 20.x
        if kind == "version":
            return type(v) is int and v == 1
        if kind in ("width", "direction", "decay"):
            return type(v) is int and v in {"width": (1, 2), "direction": (-1, 1), "decay": (0, 1, 2)}[kind]
        if kind == "tilt":
            if isinstance(v, str):
                return v in {"normal", "bigger", "biggest", "keep_normal", "keep_bigger", "keep_biggest", "zero"}
            if number(v):
                return -100 <= v <= 100
            if isinstance(v, list) and len(v) == 2:
                a, b = v
                manual = lambda n: number(n) and -100 <= n <= 100
                endpoint = lambda n: manual(n) or (isinstance(n, str) and primitive(n, "tilt"))
                if isinstance(b, list):
                    return (len(b) == 2 and all(primitive(n, "unit") for n in b)
                            and (manual(a) or (isinstance(a, list) and len(a) == 2
                                 and manual(a[0]) and endpoint(a[1]))))
                return manual(a) and endpoint(b)
            return False
        raise AssertionError(kind)

    def check(value, schema, path):
        start = len(issues)
        if isinstance(schema, str):
            if not primitive(value, schema):
                error(path, f"Expected {schema}")
        elif isinstance(schema, dict):
            if not isinstance(value, dict):
                error(path, "Expected object")
                return False
            known = {key.removesuffix("?") for key in schema}
            for field, child in schema.items():
                key = field.removesuffix("?")
                if key in value:
                    check(value[key], child, path + "." + key)
                elif not field.endswith("?"):
                    error(path + "." + key, "Required field is missing")
            for key in value.keys() - known:
                issues.append(Issue("warning", path + "." + str(key), "Unknown field"))
        else:
            tag, *args = schema
            if tag == "union":
                for variant in args:
                    if check(value, variant, path):
                        del issues[start:]
                        return True
                    del issues[start:]
                error(path, "Value does not match any allowed type")
            elif tag == "dict":
                if not isinstance(value, dict):
                    error(path, "Expected object")
                else:
                    for key, child in value.items():
                        check(child, args[0], path + "[" + json.dumps(key) + "]")
            elif not isinstance(value, list):
                error(path, "Expected array")
            elif tag == "tuple":
                required = sum(not (isinstance(a, tuple) and a[0] == "optional") for a in args)
                if not required <= len(value) <= len(args):
                    error(path, f"Expected array size {required}" + (f"-{len(args)}" if required != len(args) else ""))
                for i, (child, desc) in enumerate(zip(value, args)):
                    check(child, desc[1] if isinstance(desc, tuple) and desc[0] == "optional" else desc, f"{path}[{i}]")
            elif tag in ("array", "events"):
                if tag == "array":
                    if len(value) < args[1] or (args[2] is not None and len(value) > args[2]):
                        error(path, f"Invalid array size {len(value)}")
                elif "nonempty" in args and not value:
                    error(path, "At least one event is required")
                for i, child in enumerate(value):
                    check(child, args[0], f"{path}[{i}]")
                if tag == "events":
                    keys = [v[0] if isinstance(v, list) and v else v for v in value]
                    if all(uint(k) for k in keys):
                        if any(a > b for a, b in zip(keys, keys[1:])):
                            error(path, "Events must be ordered by y/ry/idx")
                        if "relative" in args and (not keys or keys[0] != 0):
                            error(path, "First relative point must have ry == 0")
        return not any(i.level == "error" for i in issues[start:])

    def no_null(value, path):
        if value is None:
            error(path, "Null is not allowed")
        elif isinstance(value, dict):
            for key, child in value.items():
                no_null(child, path + "." + str(key))
        elif isinstance(value, list):
            for i, child in enumerate(value):
                no_null(child, f"{path}[{i}]")

    no_null(chart, "$")
    check(chart, _SCHEMA, "$")
    if not isinstance(chart, dict) or not isinstance(chart.get("note"), dict):
        return issues
    for kind in ("bt", "fx", "laser"):
        lanes = chart["note"].get(kind, [])
        if not isinstance(lanes, list):
            continue
        for lane_idx, lane in enumerate(lanes):
            if not isinstance(lane, list):
                continue
            previous_start, previous_end = -1, -1
            for i, note in enumerate(lane):
                path = f"$.note.{kind}[{lane_idx}][{i}]"
                if kind == "laser":
                    if not isinstance(note, list) or len(note) not in (2, 3) or not uint(note[0]) or not isinstance(note[1], list):
                        continue
                    y, points = note[:2]
                    end = y
                    for j, point in enumerate(points):
                        if not isinstance(point, list) or len(point) < 2:
                            continue
                        if uint(point[0]):
                            end = max(end, y + point[0])
                        vals = point[1] if isinstance(point[1], list) else [point[1]]
                        if any(not primitive(v, "unit") for v in vals):
                            error(f"{path}[1][{j}][1]", "Laser values must be in [0, 1]")
                elif uint(note):
                    y = end = note
                elif isinstance(note, list) and len(note) == 2 and all(uint(v) for v in note):
                    y, length = note
                    end = y + length
                else:
                    continue
                if y < previous_end or y == previous_start:
                    error(path, "Notes overlap on the same lane")
                previous_start, previous_end = y, max(previous_end, end)
    return issues
