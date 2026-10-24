import {timingMap} from './timing.js';
import * as ops from './chartops.js';
import {Highway} from './highway.js';
import {Playback} from './playback.js';

const $ = id => document.getElementById(id);
const view = new Highway($('highway'));
let chart, timing, history, transport, saved, clipboard, analysis, tickEvents = [];
let revision = 0, lintRequest = 0;
const status = (message, error = false) => { $('status').textContent = message; $('status').classList.toggle('error', error); };
function explain(data) {
  return data.issues?.map(i => `${i.path}: ${i.message}`).join('\n') || data.error || 'Request failed';
}
async function api(path, method, body) {
  const response = await fetch(`/api/${path}`, {method, headers: {'Content-Type': 'application/json'},
    body: body === undefined ? undefined : JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(explain(data));
  return data;
}
const safe = fn => (...args) => Promise.resolve().then(() => fn(...args)).catch(e => status(e.message, true));
function updateDirty() {
  const dirty = JSON.stringify(chart) !== saved;
  $('dirty').textContent = dirty ? 'Unsaved changes' : 'Saved';
  document.title = `${dirty ? '* ' : ''}${chart.meta.title} · ksmauto`;
}
function metadata() {
  for (const input of $('metadata').elements)
    input.value = input.name === 'offset' ? chart.audio?.bgm?.offset || 0 : chart.meta[input.name];
}
function buildTicks() {
  tickEvents = [];
  if ($('hits').checked) for (const ref of ops.entries(chart)) {
    const pulses = ref.kind === 'laser'
      ? ref.note[1].filter(p => ops.values(p[1])[0] !== ops.values(p[1])[1]).map(p => ref.note[0] + p[0])
      : [ops.bounds(ref.kind, ref.note)[0]];
    for (const p of pulses) tickEvents.push([timing.pulseToSec(p), 1500, 0.045]);
  }
  transport.clearTicks();
}
function replace(next) {
  chart = next; revision++;
  timing = timingMap(chart.beat, chart.audio?.bgm?.offset || 0);
  transport?.configure(chart, timing);
  view.chart = chart; view.timing = timing; view.selection = [];
  $('title').textContent = `${chart.meta.title} / ${chart.meta.artist}`;
  metadata(); updateDirty(); buildTicks(); updateOnsets(); view.draw();
}
function edit(operation, message = 'Chart updated.') {
  try {
    if (transport.playing) transport.pause();
    syncPlayButton();
    const next = operation();
    if (history.push(next)) replace(next);
    status(message);
    syncPlayButton();
  } catch (e) { status(e.message, true); }
}
function syncPlayButton() { $('play').textContent = transport.playing ? 'Ⅱ Pause' : '▶ Play'; }
async function togglePlay() {
  if (transport.playing) transport.pause();
  else { if ($('hits').checked || $('metro').checked) await transport.enableSound(); await transport.play(); }
  syncPlayButton();
}
async function seek(pulse) {
  await transport.seek(pulse);
  view.playhead = transport.pulse(); view.scroll = Math.max(0, pulse);
  view.draw(); syncPlayButton();
}
async function refresh() {
  const request = ++lintRequest, version = revision;
  const data = await api('lint', 'POST', chart);
  if (request !== lintRequest || version !== revision) return;
  $('stats').replaceChildren();
  for (const [name, value] of Object.entries(data.stats)) {
    if (typeof value === 'object') continue;
    const dt = document.createElement('dt'), dd = document.createElement('dd');
    dt.textContent = name.replaceAll('_', ' ');
    dd.textContent = typeof value === 'number' ? String(Math.round(value * 100) / 100) : String(value);
    $('stats').append(dt, dd);
  }
  $('findings').replaceChildren();
  for (const finding of data.findings) {
    const item = document.createElement('button'), label = document.createElement('b'), text = document.createElement('span');
    label.textContent = `${finding.where} · ${finding.rule}`;
    text.textContent = `${finding.level}: ${finding.message}`;
    item.append(label, text);
    const match = /^m(\d+)/.exec(finding.where);
    item.disabled = !match;
    item.onclick = safe(() => seek(timing.measureToPulse(Number(match[1]))));
    $('findings').append(item);
  }
  if (!data.findings.length) $('findings').textContent = 'No lint findings.';
}
async function save() {
  $('save').disabled = true;
  const snapshot = ops.clone(chart);
  try {
    const data = await api('chart', 'PUT', snapshot);
    saved = JSON.stringify(snapshot); updateDirty();
    status(`Saved ${data.saved}${data.warnings.length ? '\n' + data.warnings.map(w => `${w.path}: ${w.message}`).join('\n') : ''}`);
    await refresh();
  } finally { $('save').disabled = false; }
}
async function loadDraft() {
  const data = await api('decompile', 'POST', chart);
  $('draft').value = data.text;
  $('draft-errors').textContent = data.warnings.join('\n');
}
async function applyDraft() {
  const data = await api('compile', 'POST', {text: $('draft').value, base: chart});
  $('draft-errors').textContent = data.errors.map(e => `Line ${e.line}:${e.col}: ${e.message}`).join('\n');
  if (!data.errors.length) edit(() => data.chart, 'Draft applied.');
}
function updateOnsets() {
  view.onsets = [];
  if (!analysis) return;
  const den = analysis.tempo.time_sig[1];
  for (const m of analysis.measures) {
    let bpm = analysis.tempo.bpm;
    for (const change of analysis.tempo.changes || []) if (change.measure <= m.index) bpm = change.bpm;
    for (const [beat, strength] of m.onsets.all)
      view.onsets.push([timing.audioToPulse(m.start_sec + beat * 4 / den * 60 / bpm), strength]);
  }
}
function snapped(y) { return timing.snap(view.pulse(y), Number($('snap').value)); }
function coordinates(event) {
  const rect = view.canvas.getBoundingClientRect();
  return [event.clientX - rect.left, event.clientY - rect.top];
}
function pointerDown(event) {
  if (event.button !== 0 && event.button !== 2) return;
  view.canvas.focus();
  const [x, y] = coordinates(event), tool = $('tool').value, pulse = snapped(y);
  const side = Number($('side').value);
  if (tool === 'laser' && event.button === 2) {
    const hit = view.pointAt(x, y, side);
    if (hit) edit(() => ops.deleteLaserPoint(chart, side, hit.section, hit.point), 'Laser point deleted.');
    return;
  }
  if (event.button !== 0) return;
  if (x < view.outerLeft - 6 || x > view.outerLeft + view.outerWidth + 6) {
    safe(() => seek(Math.max(0, view.pulse(y))))(); return;
  }
  if (transport.playing) { transport.pause(); syncPlayButton(); }
  let gesture;
  if (tool === 'select') gesture = {type: 'select', x, pulse, currentX: x, current: pulse};
  else if (tool === 'bt' || tool === 'fx') {
    const lane = view.lane(x, tool);
    if (lane < 0) return;
    gesture = {type: 'button', kind: tool, lane, pulse, current: pulse};
  } else {
    const hit = view.pointAt(x, y, side);
    if (hit && !event.shiftKey) gesture = {type: 'point', side, ...hit, x, currentX: x};
    else {
      const width = Number($('width').value), [m] = timing.pulseToMeasure(pulse);
      const step = (timing.measureToPulse(m + 1) - timing.measureToPulse(m)) / Number($('snap').value);
      edit(() => ops.addLaser(chart, side, pulse, view.laserValue(x, width), step, width, event.shiftKey), 'Laser point added.');
      return;
    }
  }
  view.gesture = gesture;
  view.canvas.setPointerCapture(event.pointerId); view.draw();
}
function pointerMove(event) {
  const g = view.gesture;
  if (!g) return;
  const [x, y] = coordinates(event);
  g.current = snapped(y); g.currentX = x;
  view.draw();
  if (g.type === 'point') {
    // Preview without changing the chart or adding history states.
    view.chart = ops.moveLaserPoint(chart, g.side, g.section, g.point, view.laserValue(x, g.width), g.endpoint);
    view.draw(); view.chart = chart;
  }
}
function pointerUp(event) {
  const g = view.gesture;
  if (!g) return;
  pointerMove(event); view.gesture = null;
  if (g.type === 'button') edit(() => ops.toggleButton(chart, g.kind, g.lane, g.pulse, g.current), 'Button notes updated.');
  else if (g.type === 'point') {
    if (Math.abs(g.currentX - g.x) > 2)
      edit(() => ops.moveLaserPoint(chart, g.side, g.section, g.point, view.laserValue(g.currentX, g.width), g.endpoint), 'Laser value updated.');
  } else {
    view.selection = ops.selectRange(chart, g.pulse, g.current, ref => view.inRectangle(ref, g.x, g.currentX));
    status(`${view.selection.length} note(s) selected.`);
  }
  view.draw();
}
function undo(redo = false) {
  transport.pause(); syncPlayButton();
  replace(redo ? history.redo() : history.undo()); status(redo ? 'Redo.' : 'Undo.');
}
function keydown(event) {
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(event.target.tagName);
  const ctrl = event.ctrlKey || event.metaKey, key = event.key.toLowerCase();
  if (ctrl && key === 's') { event.preventDefault(); safe(save)(); return; }
  if (typing) return;
  if (event.code === 'Space') { event.preventDefault(); safe(togglePlay)(); }
  else if (ctrl && (key === 'z' || key === 'y')) { event.preventDefault(); undo(key === 'y' || event.shiftKey); }
  else if (key === 'delete' || key === 'backspace') {
    event.preventDefault(); edit(() => ops.deleteSelection(chart, view.selection), 'Selection deleted.');
  } else if (ctrl && key === 'c') {
    event.preventDefault();
    if (!view.selection.length) { status('Select notes to copy.'); return; }
    const first = Math.min(...view.selection.map(ref => ops.bounds(ref.kind, chart.note[ref.kind][ref.lane][ref.index])[0]));
    clipboard = ops.copySelection(chart, view.selection, timing.measureToPulse(timing.pulseToMeasure(first)[0]));
    status(`Copied ${clipboard.notes.length} note(s).`);
  } else if (ctrl && key === 'v') {
    event.preventDefault();
    if (clipboard) edit(() => ops.pasteSelection(chart, clipboard, timing.measureToPulse(timing.pulseToMeasure(transport.pulse())[0])), 'Selection pasted.');
  } else if (key === 'm') edit(() => ops.mirrorSelection(chart, view.selection), 'Selection mirrored.');
  else if (key === 'l') { $('side').value = String(1 - Number($('side').value)); status(`Laser side: ${$('side').selectedOptions[0].textContent}`); }
}
function frame() {
  if (transport) {
    transport.frame();
    const p = transport.pulse(); view.playhead = p;
    if (transport.playing) {
      view.scroll = Math.max(0, p - (view.h / view.scale) * 0.16);
      const events = [...tickEvents];
      if ($('metro').checked) {
        const [m] = timing.pulseToMeasure(p);
        for (let measure = Math.max(0, m); measure <= m + 1; measure++) {
          const [n, d] = timing.signatureAt(measure), start = timing.measureToPulse(measure);
          for (let b = 0; b < n; b++) events.push([timing.pulseToSec(start + b * 960 / d), b ? 900 : 1200, 0.06]);
        }
      }
      transport.schedule(events); view.draw();
    }
    $('position').textContent = `m${timing.pulseToMeasure(Math.max(0, p))[0]} · ${timing.pulseToAudio(p).toFixed(2)} s`;
  }
  requestAnimationFrame(frame);
}
async function init() {
  const response = await fetch('/api/chart');
  if (!response.ok) throw new Error(explain(await response.json()));
  chart = await response.json();
  const hasAudio = response.headers.get('X-Editor-Audio') === 'true';
  transport = new Playback($('audio'), hasAudio);
  transport.onError = e => { status(e.message, true); syncPlayButton(); };
  if (hasAudio) $('audio').src = '/api/audio';
  $('audio-status').textContent = hasAudio ? 'Audio connected' : 'No audio · silent preview';
  $('audio').onended = () => { transport.pause(); syncPlayButton(); view.draw(); };
  $('audio').onerror = () => { transport.pause(); syncPlayButton(); status('Audio could not be decoded by this browser.', true); };
  if (response.headers.get('X-Editor-Analysis') === 'true') analysis = await api('analysis', 'GET');
  else { $('onsets').disabled = true; $('onsets').parentElement.title = 'Start with --analysis to show onsets'; }
  saved = JSON.stringify(chart); history = ops.history(chart);
  replace(chart); view.resize(); view.grid = Number($('snap').value); view.draw();
  new ResizeObserver(() => { view.resize(); view.draw(); }).observe(view.canvas.parentElement);
  $('save').onclick = safe(save); $('play').onclick = safe(togglePlay);
  $('rate').onchange = safe(async () => { await transport.setRate(Number($('rate').value)); syncPlayButton(); });
  for (const id of ['metro', 'hits']) $(id).onchange = safe(async () => {
    if ($(id).checked) await transport.enableSound(); buildTicks();
  });
  $('onsets').onchange = () => { view.showOnsets = $('onsets').checked; view.draw(); };
  $('snap').onchange = () => { view.grid = Number($('snap').value); view.draw(); };
  $('undo').onclick = () => undo(); $('redo').onclick = () => undo(true);
  $('refresh').onclick = safe(refresh);
  $('metadata').onsubmit = e => e.preventDefault();
  $('metadata').onchange = event => {
    const {name, value} = event.target;
    if (!event.target.checkValidity()) { event.target.reportValidity(); return; }
    edit(() => {
      const next = ops.clone(chart);
      if (name === 'offset') { next.audio ||= {}; next.audio.bgm ||= {}; next.audio.bgm.offset = Number(value); }
      else next.meta[name] = ['difficulty', 'level'].includes(name) && /^\d+$/.test(value) ? Number(value) : value;
      return next;
    }, 'Metadata updated.');
  };
  $('draft-tab').onclick = safe(async () => {
    $('inspector').hidden = true; $('draft-panel').hidden = false;
    $('draft-tab').classList.add('active'); $('inspect-tab').classList.remove('active');
    if (!$('draft').value) await loadDraft();
  });
  $('inspect-tab').onclick = () => {
    $('inspector').hidden = false; $('draft-panel').hidden = true;
    $('draft-tab').classList.remove('active'); $('inspect-tab').classList.add('active');
  };
  $('decompile').onclick = safe(loadDraft); $('apply').onclick = safe(applyDraft);
  view.canvas.onpointerdown = pointerDown; view.canvas.onpointermove = pointerMove;
  view.canvas.onpointerup = pointerUp;
  view.canvas.onpointercancel = () => { view.gesture = null; view.draw(); };
  view.canvas.oncontextmenu = e => e.preventDefault();
  view.canvas.addEventListener('wheel', event => {
    event.preventDefault();
    if (event.ctrlKey || event.metaKey) {
      const [, y] = coordinates(event), anchor = view.pulse(y);
      view.scale = Math.max(0.05, Math.min(2.4, view.scale * Math.exp(-event.deltaY * 0.002)));
      view.scroll = Math.max(0, anchor - (view.h - 36 - y) / view.scale);
      $('zoom').textContent = `${Math.round(view.scale / 0.3 * 100)}%`;
    } else view.scroll = Math.max(0, view.scroll - event.deltaY / view.scale);
    view.draw();
  }, {passive: false});
  document.addEventListener('keydown', keydown);
  window.addEventListener('beforeunload', e => {
    if (JSON.stringify(chart) !== saved) { e.preventDefault(); e.returnValue = ''; }
  });
  await refresh(); status('Ready. Measure numbers start at 0.'); requestAnimationFrame(frame);
}
init().catch(e => status(e.message, true));
