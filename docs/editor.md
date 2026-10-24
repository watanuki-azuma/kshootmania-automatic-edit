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
To share a chart with its audio as one HTML file, run:

```sh
uv run ksmauto preview chart.ksh --audio song.ogg -o preview.html
```

The page is the released `index.html` of
[KSM-WEB-VIEWER](https://github.com/watanuki-azuma/KSM-WEB-VIEWER), vendored as
`src/ksmauto/viewer.html`; its playback behavior is documented there
(`docs/behavior.md`), and the viewer's own tests live in that repository. To
take a newer release, run `uv run python scripts/update_viewer.py vX.Y.Z`. The
viewer without an embedded chart is published at
https://watanuki-azuma.github.io/KSM-WEB-VIEWER/.

Keep one editing tab per server session; saving from multiple tabs uses the last
successful save.

`uv run pytest tests/test_editor.py` includes HTTP integration tests, pure ES
module tests through Node's test runner, and a Chromium smoke test using Node
Playwright. Missing Node/Playwright/Chromium or a sandbox that forbids loopback
sockets skips the corresponding integration tests. HTTP handler tests also run
in memory without sockets. A completed browser smoke test writes
`out/editor-preview.png`.

`uv run pytest tests/test_preview.py` checks the embedding and compares the
viewer's KSH converter with the Python importer (with the local corpus when
present).
