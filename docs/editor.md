# Browser editor

```sh
uv run ksmauto edit chart.kson --audio song.ogg --analysis analysis.json
uv run ksmauto edit chart.ksh --no-browser --port 8765
```

The editor serves one chart at the printed `http://127.0.0.1:PORT/` URL. Close it
with Ctrl+C in the terminal. It needs no frontend build, external libraries, or
Python extras. Audio decoding uses the browser's supported formats. Without an
audio file it offers silent preview playback. `--audio` overrides the chart's
`audio.bgm.filename`, which is otherwise relative to the input chart directory.

KSH and draft inputs are converted in memory and saved next to the input with a
`.kson` suffix. The original input is preserved. Before overwriting an existing
KSON, its bytes are copied to `NAME.kson.bak` once per server session. Later saves
in that session preserve the backup. Saving validates the entire chart; rejected
edits do not change the saved file. The UI marks unsaved changes and warns before
closing a tab that contains them.

Time runs upward. Measure numbers start at zero. The pulse/seconds map accounts
for BPM and time signature changes, with
`audio_sec = chart_sec + audio.bgm.offset / 1000`.

- Space plays/pauses; the speed selector offers 0.5×, 0.75×, and 1×. Click a
  timeline margin to seek. Wheel up scrolls forward; Ctrl+wheel zooms around the
  pointer. Metronome and note ticks use WebAudio. Onsets require `--analysis`.
- Snap is divisions **per measure** (4–48), including triplet grids. BT/FX tools
  toggle a note at the snapped position. Drag in either vertical direction to
  create a long note. Overlaps on a lane are rejected.
- Laser points use values in steps of 1/50. Choose a side (or press L) and width.
  A point within one grid step after a section's end extends it; a larger gap
  starts a section. Shift+click at its last point's time sets the slam endpoint.
  Drag a point horizontally to change its value. Each slam endpoint can be
  dragged independently. Right-click a point to delete it.
- Select by dragging a rectangle; intersecting long notes and laser sections are
  selected as whole notes/sections. Delete removes the selection, M mirrors it.
  Ctrl+C copies it relative to its first measure; Ctrl+V pastes at the playhead's
  measure, preserving pulse distances. Pasting into a different time signature
  therefore preserves pulse distances rather than rescaling the rhythm.
- Ctrl+Z / Ctrl+Y undo/redo up to 100 chart snapshots. Metadata and successful
  draft application participate in the same history. Ctrl+S saves, then refreshes
  lint and statistics. Click a located lint finding to jump to its measure.

The Draft text tab decompiles the current chart. Reload updates the text from the
chart; Apply compiles using the current chart as the base. Review decompiler
warnings about unsupported data, including laser curves, before applying. The
existing draft format's conversion behavior applies unchanged. Error messages
include line and column numbers.

The editor canvas remains a placement view; its playback uses the BPM map.
For the standalone chart viewer, run:

```sh
uv run ksmauto viewer -o viewer.html
uv run ksmauto preview chart.ksh --audio song.ogg -o preview.html
```

Both commands use the same self-contained page. `viewer` starts with a file picker;
`preview` embeds the chart and optional audio. Open KSON/KSH and audio in either
order, together, or by dropping a folder. Audio is matched against
`audio.bgm.filename`, with a fallback when there is only one audio file. Opening
another chart replaces playback without reloading. KSH decoding supports UTF-8
and Windows Shift_JIS. No server or external URLs are required, including in a
sandboxed iframe with scripts enabled. Audio format support depends on the browser.

The viewer supports KSON auto/manual tilt (including keep, immediate changes and
quadratic curves), camera body graphs (`zoom_top`, `zoom_bottom`, `zoom_side`,
`rotation_deg`, `center_split`), slam spin/half-spin/swing, and the default slam
shake. Highway and judgment-line rotations are evaluated separately. KSH before
version 167 uses the legacy zoom formulas. Camera smoothing is sampled at 120 Hz
in chart time so pause, seeking and slowed playback show a repeatable camera pose;
this approximates KSM's frame-driven smoothing. The procedural judgment line and
cursor approximate the original textured planes and billboards.

Both 2D and 3D use the same highway drawing and account for `beat.scroll_speed`
(including curves and reverse scroll) and `beat.stop`. Stops freeze scroll for
the specified pulse interval; audio and camera time continue. The seek bar is in
measures. Play/pause, 0.5/0.75/1× playback, hi-speed and effects remain available.
FX/laser audio effects and built-in FX key sounds use the existing approximate
synthesis, independently of scroll. The default-on 「直角音」 checkbox plays laser
slam sounds even without BGM. A short band-pass noise burst and pitched click
approximate the default hit and the up/down/swing variants; mute is silent. The
viewer follows KSM v2's note-time playback: `audio.key_sound.laser.vol` changes
apply at the slam pulse (default 0.5), and `legacy.vol_auto` scales volume by
`min(1, abs(vf - v) * section_width * 2)`. Simultaneous slams use the louder lane.
Only events at actual slam pulses apply. Both KSON `slam_up`/`slam_down`/
`slam_swing`/`slam_mute` and the KSH converter's `up`/`down`/`swing`/`mute` names
are recognized; KSH `chokkakuvol` and `chokkakuautovol` are preserved. Sounds share
the FX key sound output level, independently of BGM's `vol`, and follow the audio
clock through speed changes and seeking. KSM's sound assets are not bundled or
used; unsupported custom slam sounds fall back to the default hit.
Backgrounds, layers, movies, original skin assets, judging, scoring and gameplay
input are not reproduced. Custom sound files
and `switch_audio` are not synthesized.

Keep one editing tab per server session; saving from multiple tabs uses the last
successful save.

`uv run pytest tests/test_editor.py` includes HTTP integration tests, pure ES
module tests through Node's test runner, and a Chromium smoke test using Node
Playwright. Missing Node/Playwright/Chromium or a sandbox that forbids loopback
sockets skips the corresponding integration tests. HTTP handler tests also run
in memory without sockets. A completed browser smoke test writes
`out/editor-preview.png`.

`uv run pytest tests/test_preview.py` also checks the standalone CLI, compares the
browser KSH converter with the Python importer, runs Node camera/scroll and slam
sound event/scheduling tests, and exercises file loading and playback with
Playwright. The local corpus is
optional. Browser checks skip when Chromium is absent or the sandbox forbids
launching it. A successful smoke test writes `out/viewer-preview.png`.
