import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const html = fs.readFileSync(new URL('../src/ksmauto/preview_template.html', import.meta.url), 'utf8');
const core = vm.runInNewContext(html.match(/<script id="viewer-core">([\s\S]*?)<\/script>/)[1] + '\n({curveAt, graphAt, tiltAt, newTilt, stepTilt, patternAt, slamShake, highwayCorners, scrollMap, expandGraph, laserValueAt, effectiveStdBpm})');
const close = (a, b, eps = 1e-8) => assert.ok(Math.abs(a - b) < eps, `${a} != ${b}`);
const laser = (side, points) => ({side, graph: points, pts: points.map(([y, v]) => ({y, a: Array.isArray(v) ? v[0] : v, b: Array.isArray(v) ? v[1] : v}))});

test('GraphPoint incoming/outgoing, defaults, pre-first, final and quadratic curves', () => {
  close(core.graphAt([], 0), 0);
  const graph = [[100, [2, 4], [0.5, 1]], [200, [8, 10]]];
  close(core.graphAt(graph, 0), 2); close(core.graphAt(graph, 100), 4);
  close(core.graphAt(graph, 100, 0, true), 2);
  close(core.graphAt(graph, 150), 7); close(core.graphAt(graph, 200), 10);
  close(core.graphAt(graph, 200, 0, true), 8); close(core.graphAt(graph, 300), 10);
  for (const a of [0, 0.25, 0.5, 1]) { close(core.curveAt([a, a], 0.3), 0.3); close(core.curveAt([a, 0.7], 0), 0); close(core.curveAt([a, 0.7], 1), 1); }
});

test('all manual tilt encodings, curves, immediate manual to auto and retained auto type', () => {
  const events = [[0, 'biggest'], [100, [1, [0.5, 1]]], [200, [[3, 4], [0.5, 0]]], [300, [6, 'keep_bigger']], [400, 'zero']];
  assert.equal(core.tiltAt(events, 50).manual, null);
  close(core.tiltAt(events, 100).manual, 1); close(core.tiltAt(events, 150).manual, 2.5);
  close(core.tiltAt(events, 250).manual, 4.5);
  close(core.tiltAt(events, 250).scale, 2.5);
  assert.equal(core.tiltAt(events, 300).manual, null);
  assert.equal(core.tiltAt(events, 300).keep, true); close(core.tiltAt(events, 300).scale, 1.75);
  close(core.tiltAt(events, 400).scale, 0);
  close(core.tiltAt([[0, [1, 2]], [100, 4]], 50).manual, 3);
});

test('auto tilt uses one section per lane, 480-pulse lookahead, cancellation and wide-independent values', () => {
  const l = laser(0, [[600, 0.8], [960, 0.8]]), future = laser(0, [[1000, 1], [1200, 1]]);
  let s = core.newTilt(); close(core.stepTilt(s, [l], [], 119, 0.1), 0);
  close(core.stepTilt(s, [l, future], [], 120, 0.1), 0.45 * Math.PI / 18);
  core.stepTilt(s, [l, future], [], 700, 1); close(s.factor, 0.8);
  s = core.newTilt(); core.stepTilt(s, [l, laser(1, [[600, 0.2], [960, 0.2]])], [], 700, 1); close(s.factor, 0);
  close(core.laserValueAt(laser(0, [[0, [0, 1]], [240, 0]]), 0), 1);
});

test('KSM scale slew, keep reversal threshold, slow return and 40ms manual crossfade', () => {
  const l = laser(0, [[0, 1], [240, 1]]), s = core.newTilt();
  core.stepTilt(s, [l], [[0, 'biggest']], 0, 0.1); close(s.factor, 0.45); close(s.scale, 1.4);
  core.stepTilt(s, [l], [[0, 'keep_biggest']], 0, 1); close(s.factor, 1);
  core.stepTilt(s, [], [[0, 'keep_biggest']], 500, 0.1); close(s.factor, 1);
  core.stepTilt(s, [laser(1, [[0, 0], [960, 0]])], [[0, 'keep_biggest']], 500, 0.1); close(s.factor, 1);
  core.stepTilt(s, [], [[0, 'normal']], 500, 0.1); close(s.factor, 0.91);
  const m = core.newTilt(); core.stepTilt(m, [], [[0, 2]], 0, 0.02); close(m.blend, 0.5);
  close(core.stepTilt(m, [], [[0, 2]], 0, 0.02), 2 * Math.PI / 18);
  core.stepTilt(m, [], [[0, [2, 'zero']]], 0, 0.02); close(m.blend, 0.5);
  close(core.stepTilt(m, [], [[0, [2, 'zero']]], 0, 0.02), 0);
});

test('spin, half spin and swing match KSM formulas and require matching slam direction', () => {
  const slams = [{y: 0, d: 1, t: 0}];
  close(core.patternAt({spin: [[0, -1, 675]]}, slams, 360).highway, 0);
  close(core.patternAt({spin: [[0, 1, 675]]}, slams, 360).highway, 0); // full turn, wrapped to zero by the next piece
  close(core.patternAt({spin: [[0, 1, 675]]}, slams, 180).highway, -Math.sin(0.375) / Math.sin(0.75) * 360);
  close(core.patternAt({half_spin: [[0, 1, 400]]}, slams, 110).highway, -60);
  close(core.patternAt({half_spin: [[0, 1, 400]]}, slams, 100).jdgline, -20);
  for (const decay of [0, 1, 2]) close(core.patternAt({swing: [[0, 1, 400, {scale: 100, repeat: 1, decay_order: decay}]]}, slams, 200).shift, 10 * 0.5 ** decay);
  close(core.slamShake(slams, {}, 0.075), (17 * 50 / 150 / 2) / 4);
  close(core.slamShake(slams, {swing: [[0, 1, 400]]}, 0.075), 0);
  close(core.slamShake(slams, {}, 0.15), 0);
});

test('scroll integrates immediate and curved speeds; stop ranges merge and override speed without changing time', () => {
  const s = core.scrollMap({scroll_speed: [[0, 1], [240, [1, 2]], [480, 2]], stop: [[60, 120], [120, 120]]});
  close(s.distance(0, 60), 60); close(s.distance(60, 240), 0);
  close(s.distance(240, 480), 480); close(s.distance(480, 240), -480);
  const reverse = core.scrollMap({scroll_speed: [[0, -1], [240, -1]]}); close(reverse.distance(0, 240), -240);
  const curved = core.scrollMap({scroll_speed: [[0, 0, [0.5, 1]], [240, 1]]});
  const expanded = core.expandGraph([[0, 0, [0.5, 1]], [240, 1]]);
  assert.equal(expanded.length, 17);
  close(curved.distance(0, 240), 159.84375);
});

test('highway neutral plane, modern 2400-unit turn and asymmetric bottom zoom', () => {
  const neutral = core.highwayCorners({zoom_top: 0, zoom_bottom: 0});
  const full = core.highwayCorners({zoom_top: 2400, zoom_bottom: 0});
  for (let i = 0; i < 4; i++) for (let j = 0; j < 3; j++) close(neutral[i][j], full[i][j]);
  const top = core.highwayCorners({zoom_top: 600, zoom_bottom: 0}); assert.ok(top[0][1] > 200);
  const positive = core.highwayCorners({zoom_top: 0, zoom_bottom: 100});
  const negative = core.highwayCorners({zoom_top: 0, zoom_bottom: -100});
  close((negative[2][1] - neutral[2][1]) / (positive[2][1] - neutral[2][1]), -2.5);
});

function viewerPage(chart = null) {
  let ms = 0, serial = 0;
  const frames = new Map(), elements = new Map(), audios = [], processors = [], uploads = [];
  const drawing = new Proxy({createLinearGradient: () => ({addColorStop() {}})}, {get: (obj, key) => obj[key] ?? (() => {})});
  const gl = new Proxy({
    getExtension: () => null, getParameter: () => 8,
    bufferData: (target, values) => { assert.ok([...values].every(Number.isFinite), 'camera projection must stay finite'); uploads.push([...values]); },
  }, {get: (obj, key) => obj[key] ?? (() => ({}))});
  const element = id => {
    if (!elements.has(id)) elements.set(id, {value: ({view:'3d',rate:'1',hispeed:'6.5',vis:'0',seek:'0'})[id] || '', checked:false,
      style:{}, textContent:'', disabled:false, hidden:false, append() {}, replaceChildren() {},
      getContext: kind => kind === 'webgl' ? gl : drawing,
      getBoundingClientRect: () => ({width:560,height:680})});
    return elements.get(id);
  };
  class Audio {
    constructor() { this.paused = true; this.base = 0; this.at = 0; this.playbackRate = 1; audios.push(this); }
    get currentTime() { return this.base + (this.paused ? 0 : (ms - this.at) / 1000 * this.playbackRate); }
    set currentTime(v) { this.base = v; this.at = ms; }
    async play() { this.at = ms; this.paused = false; }
    pause() { this.base = this.currentTime; this.paused = true; }
    load() {} addEventListener() {} removeAttribute() {}
  }
  class AudioContext {
    constructor() { this.currentTime = 0; this.audioWorklet = {addModule: async () => {}}; }
    async resume() {} async close() { this.closed = true; }
    createMediaElementSource() { return {connect: n => ({connect() {}})}; }
  }
  class AudioWorkletNode {
    constructor() { this.messages = []; this.port = {postMessage: m => this.messages.push(m)}; processors.push(this); }
    connect() { return this; }
  }
  element('chart-data').textContent = JSON.stringify(chart);
  element('fx-worklet').textContent = html.match(/<script id="fx-worklet" type="text\/plain">([\s\S]*?)<\/script>/)[1];
  const context = vm.createContext({console, Audio, AudioContext, AudioWorkletNode, AbortController, TextDecoder, URL, Blob, devicePixelRatio:1,
    performance: {now: () => ms}, localStorage: {getItem: () => null, setItem() {}},
    matchMedia: () => ({matches:false}), ResizeObserver: class {observe() {} disconnect() {}},
    requestAnimationFrame: fn => { frames.set(++serial, fn); return serial; }, cancelAnimationFrame: id => frames.delete(id),
    document: {getElementById:element, createElement:element, addEventListener() {}, body:{classList:{add() {},remove() {}}}},
  });
  for (const id of ['ksh-converter','viewer-core']) vm.runInContext(html.match(new RegExp(`<script id="${id}">([\\s\\S]*?)<\\/script>`))[1], context);
  vm.runInContext(html.match(/<script>\n([\s\S]*?)<\/script>/)[1].replace('__AUDIO_SRC__',''), context);
  return {element, audios, processors, uploads, async open(files) { await vm.runInContext('queueFiles',context)(files); },
    async frame(delta = 16) { ms += delta; const pending = [...frames.values()]; frames.clear(); for (const fn of pending) fn(); await Promise.resolve(); }};
}
const sample = () => ({format_version:1,meta:{title:'Test'},beat:{bpm:[[0,120]]},audio:{bgm:{filename:'song.wav'}},
  note:{bt:[[[0,960]],[],[],[]],fx:[[],[]],laser:[[[0,[[0,[0,1]],[960,0]]]],[]]},
  camera:{cam:{body:{zoom_top:[[0,100]],zoom_bottom:[[0,20]],rotation_deg:[[0,20]],center_split:[[0,50]]}}}});

test('full page initializes embedded and standalone, redraws both views and replaces chart without stale audio', async () => {
  const page = viewerPage(); assert.equal(page.element('play').disabled, true);
  const file = (name, value) => new File([value], name);
  await page.open([file('song.wav','audio')]); assert.match(page.element('open-status').textContent, /保持/);
  await page.open([file('chart.kson',JSON.stringify(sample()))]);
  assert.equal(page.element('title').textContent, 'Test'); await page.frame();
  assert.ok(page.uploads.length > 0);
  await page.element('start').onclick(); await page.frame(1100);
  assert.equal(page.element('time').textContent, '0:01'); assert.equal(page.element('play').textContent, '❚❚ PAUSE');
  assert.equal(page.processors.length, 1);
  const data = page.processors[0].messages.find(m => m.type === 'data'); assert.ok(data.lasers.length > 0);
  page.element('seek').oninput({target:{value:'0.5'}}); await page.frame();
  assert.ok(page.processors[0].messages.some(m => m.type === 'reset'));
  page.element('view').onchange({target:{value:'flat'}}); await page.frame();
  const replacement = sample(); replacement.meta.title = 'Replacement';
  await page.open([file('next.kson',JSON.stringify(replacement))]); await page.frame();
  assert.equal(page.element('title').textContent, 'Replacement'); assert.equal(page.audios[0].paused, true);
  assert.equal(page.element('play').textContent, '▶ PLAY');
  await page.open([file('bad.ksh','not a chart')]); assert.match(page.element('open-status').textContent, /読み込み失敗/);
  assert.equal(page.element('title').textContent, 'Replacement');
  const embedded = viewerPage(sample()); await embedded.frame(); assert.equal(embedded.element('title').textContent, 'Test');
});

test('negative audio offset keeps chart pre-roll and scroll never changes the effect clock', async () => {
  const c = sample(); c.audio.bgm.offset = -1000; c.beat.scroll_speed = [[0,0]]; c.beat.stop = [[0,480]];
  const page = viewerPage(); await page.open([new File([JSON.stringify(c)],'chart.kson'), new File(['audio'],'song.wav')]);
  await page.element('start').onclick(); await page.frame(500);
  assert.equal(page.audios[0].paused, true);
  assert.equal(page.processors[0].messages.at(-1).chart, 0.5);
  await page.frame(600); assert.equal(page.audios[0].paused, false);
  close(page.processors[0].messages.at(-1).chart, 1.1);
  page.element('seek').oninput({target:{value:'1'}}); await Promise.resolve(); await Promise.resolve(); await page.frame();
  assert.ok(page.processors[0].messages.at(-1).chart >= 2);
});


test('O-mod standard BPM is the pulse-duration mode, with higher BPM winning ties and future changes ignored', () => {
  close(core.effectiveStdBpm({}, [[0, 120], [480, 240]], 960), 240);
  close(core.effectiveStdBpm({}, [[0, 120], [480, 240]], 600), 120);
  close(core.effectiveStdBpm({}, [[0, 120], [480, 240]], 0), 120);
  close(core.effectiveStdBpm({std_bpm: 180}, [[0, 120]], 960), 180);
});

test('KSH file input path and folder-relative audio match with multiple audio files', async () => {
  const page = viewerPage();
  const chart = new File(['title=Imported\nt=120\nm=../audio/right.wav\n--\n1000|00|0-\n0000|00|o-\n0000|00|--\n--\n'], 'chart.ksh');
  chart.viewerPath = 'folder/charts/chart.ksh';
  const right = new File(['audio'], 'right.wav'); right.viewerPath = 'folder/audio/right.wav';
  const other = new File(['audio'], 'other.wav'); other.viewerPath = 'folder/audio/other.wav';
  await page.open([other, chart, right]); await page.frame();
  assert.equal(page.element('title').textContent, 'Imported');
  assert.match(page.element('open-status').textContent, /right.wav/);
  const before = page.uploads.at(-1);
  page.element('seek').oninput({target:{value:'0.5'}}); await page.frame();
  page.element('seek').oninput({target:{value:'0'}}); await page.frame();
  assert.deepEqual(page.uploads.at(-1), before, 'seeking restores the same camera pose');
});
