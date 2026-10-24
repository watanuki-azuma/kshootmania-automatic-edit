import test from 'node:test';
import assert from 'node:assert/strict';
import {timingMap} from '../src/ksmauto/editor/timing.js';
import * as ops from '../src/ksmauto/editor/chartops.js';

const blank = () => ({beat: {bpm: [[0, 120]]}, note: {bt: [[], [], [], []], fx: [[], []], laser: [[], []]}});
const ref = (kind, lane, index) => ({kind, lane, index});
const close = (a, b) => assert.ok(Math.abs(a - b) < 1e-8, `${a} != ${b}`);

test('BPM segments, offsets, fractional pulses and negative pre-roll round trip', () => {
  const t = timingMap({bpm: [[0, 120], [480, 240], [1440, 60]]}, 500);
  for (const [pulse, sec] of [[0, 0], [240, 0.5], [480, 1], [960, 1.5], [1440, 2], [1680, 3], [-240, -0.5]]) {
    close(t.pulseToSec(pulse), sec); close(t.secToPulse(sec), pulse);
    close(t.pulseToAudio(pulse), sec + 0.5); close(t.audioToPulse(sec + 0.5), pulse);
  }
  close(t.secToPulse(t.pulseToSec(497.125)), 497.125);
  close(timingMap({bpm: [[0, 120]]}, -250).audioToPulse(0), 120);
});

test('time signatures are indexed by measure; snap uses divisions per measure', () => {
  const t = timingMap({bpm: [[0, 120]], time_sig: [[0, [4, 4]], [2, [6, 8]], [4, [7, 8]]]});
  assert.equal(t.measureToPulse(2), 1920);
  assert.equal(t.measureToPulse(3), 2640);
  assert.equal(t.measureToPulse(4), 3360);
  assert.equal(t.measureToPulse(5), 4200);
  assert.deepEqual(t.pulseToMeasure(2641), [3, 1]);
  assert.deepEqual(t.signatureAt(3), [6, 8]);
  assert.equal(t.snap(1949, 12), 1920);
  assert.equal(t.snap(1951, 12), 1980);
  assert.equal(t.snap(2639, 12), 2640);
  assert.equal(t.snap(-99, 16), 0);
  assert.equal(timingMap({bpm: [[0, 120]], time_sig: [[2, [3, 4]]]}).measureToPulse(3), 2640);
});

test('chips toggle, upward and downward long drags, lane overlap rejection is atomic', () => {
  const source = blank();
  let c = ops.toggleButton(source, 'bt', 0, 240);
  assert.deepEqual(source, blank());
  assert.deepEqual(c.note.bt[0], [240]);
  c = ops.toggleButton(c, 'bt', 0, 240);
  assert.deepEqual(c.note.bt[0], []);
  c = ops.toggleButton(c, 'fx', 1, 480, 240);
  assert.deepEqual(c.note.fx[1], [[240, 240]]);
  assert.throws(() => ops.toggleButton(c, 'fx', 1, 360), /overlap/);
  assert.throws(() => ops.toggleButton(c, 'fx', 1, 120, 360), /overlap/);
  assert.deepEqual(c.note.fx[1], [[240, 240]]);
  assert.deepEqual(ops.toggleButton(c, 'fx', 1, 480).note.fx[1], [[240, 240], 480]);
});

test('laser quantization, extension, slam, gap, moving endpoints, deletion/rebasing', () => {
  let c = ops.addLaser(blank(), 0, 120, 0.213, 60, 2);
  assert.deepEqual(c.note.laser[0], [[120, [[0, 0.22]], 2]]);
  c = ops.addLaser(c, 0, 180, 0.9, 60, 2);
  c = ops.addLaser(c, 0, 180, 0.2, 60, 2, true);
  assert.deepEqual(c.note.laser[0][0][1], [[0, 0.22], [60, [0.9, 0.2]]]);
  assert.throws(() => ops.addLaser(c, 0, 180, 0, 60, 2), /Shift/);
  assert.throws(() => ops.addLaser(c, 0, 150, 0, 60, 2), /overlap/);
  c = ops.moveLaserPoint(c, 0, 0, 1, 0.511, 1);
  assert.deepEqual(c.note.laser[0][0][1][1][1], [0.9, 0.52]);
  c = ops.addLaser(c, 0, 300, 2, 60, 2);
  assert.equal(c.note.laser[0].length, 2);
  assert.equal(c.note.laser[0][1][1][0][1], 1);
  c = ops.deleteLaserPoint(c, 0, 0, 0);
  assert.deepEqual(c.note.laser[0][0], [180, [[0, [0.9, 0.52]]], 2]);
  c = ops.deleteLaserPoint(c, 0, 0, 0);
  assert.equal(c.note.laser[0].length, 1);
});

test('range selection includes intersecting holds and sections; delete only selected', () => {
  let c = ops.toggleButton(blank(), 'bt', 0, 0, 240);
  c = ops.toggleButton(c, 'bt', 1, 120);
  c = ops.addLaser(c, 1, 60, 0, 60);
  c = ops.addLaser(c, 1, 120, 1, 60);
  const selected = ops.selectRange(c, 180, 120);
  assert.equal(selected.length, 3);
  assert.equal(ops.selectRange(c, 180, 120, r => r.lane === 0).length, 1);
  const deleted = ops.deleteSelection(c, selected);
  assert.equal(ops.entries(deleted).length, 0);
  assert.equal(ops.entries(c).length, 3);
});

test('copy to a measure origin keeps relative positions; collisions reject the whole paste', () => {
  let c = ops.toggleButton(blank(), 'bt', 0, 240, 480);
  c = ops.addLaser(c, 1, 120, 0.2, 60);
  const clip = ops.copySelection(c, [ref('bt', 0, 0), ref('laser', 1, 0)], 0);
  const pasted = ops.pasteSelection(c, clip, 1920);
  assert.deepEqual(pasted.note.bt[0], [[240, 240], [2160, 240]]);
  assert.equal(pasted.note.laser[1][1][0], 2040);
  assert.throws(() => ops.pasteSelection(c, clip, 0), /overlap/);
  assert.equal(ops.entries(c).length, 2);
});

test('mirror flips lanes and both slam endpoints and preserves curve/section data', () => {
  const c = blank();
  c.note.bt = [[0], [120], [], []];
  c.note.fx = [[[60, 120]], []];
  c.note.laser[0] = [[0, [[0, [0.2, 0.8], [0.3, 0.7]], [240, 0.6]], 2]];
  const refs = ops.entries(c);
  const mirrored = ops.mirrorSelection(c, refs);
  assert.deepEqual(mirrored.note.bt, [[], [], [120], [0]]);
  assert.deepEqual(mirrored.note.fx, [[], [[60, 120]]]);
  const section = mirrored.note.laser[1][0];
  close(section[1][0][1][0], 0.8); close(section[1][0][1][1], 0.2);
  assert.deepEqual(section[1][0][2], [0.3, 0.7]); assert.equal(section[2], 2);
  const twice = ops.mirrorSelection(mirrored, ops.entries(mirrored));
  close(twice.note.laser[0][0][1][1][1], 0.6);
  assert.throws(() => ops.mirrorSelection(ops.toggleButton(c, 'bt', 3, 0), [ref('bt', 0, 0)]), /overlap/);
});

test('snapshot history is independent, bounded, and discards redo after a new edit', () => {
  const c = blank(), history = ops.history(c, 3);
  let a = ops.toggleButton(c, 'bt', 0, 0);
  assert.equal(history.push(a), true); assert.equal(history.push(a), false);
  a.note.bt[0].push(120);
  assert.deepEqual(history.undo(), c);
  assert.deepEqual(history.redo().note.bt[0], [0]);
  history.undo(); history.push(ops.toggleButton(c, 'fx', 0, 0));
  assert.deepEqual(history.redo().note.fx[0], [0]);
});

test('playback follows audio time through BPM changes and keeps position across rate/seek', async () => {
  const {Playback} = await import('../src/ksmauto/editor/playback.js');
  const audio = {currentTime: 0, playbackRate: 1, playCalls: 0,
    async play() { this.playCalls++; }, pause() {}};
  const player = new Playback(audio, true);
  const chart = {beat: {bpm: [[0, 120], [480, 240]]}, audio: {bgm: {offset: 500}}};
  player.configure(chart, timingMap(chart.beat, 500));
  player.position = 240;
  await player.play();
  close(audio.currentTime, 1);
  audio.currentTime = 2;
  close(player.pulse(), 960);
  await player.setRate(0.75);
  close(player.pulse(), 960); assert.equal(audio.playbackRate, 0.75);
  player.pause(); await player.seek(480);
  close(audio.currentTime, 1.5); close(player.pulse(), 480);
});

test('pending audio play is not started twice by animation frames; pause cancels cleanly', async () => {
  const {Playback} = await import('../src/ksmauto/editor/playback.js');
  let finish;
  const audio = {currentTime: 0, calls: 0,
    play() { this.calls++; return new Promise(resolve => { finish = resolve; }); }, pause() {}};
  const player = new Playback(audio, true);
  const chart = blank(); player.configure(chart, timingMap(chart.beat));
  const playing = player.play();
  player.frame(); player.frame(); assert.equal(audio.calls, 1);
  player.pause(); finish(); await playing;
  assert.equal(player.playing, false); assert.equal(player.audioStarted, false);
});

test('overlap checking does not reorder or mutate its input', () => {
  const c = blank(); c.note.bt[0] = [480, 0, 240];
  ops.checkOverlaps(c);
  assert.deepEqual(c.note.bt[0], [480, 0, 240]);
  assert.deepEqual(ops.toggleButton(c, 'bt', 0, 120).note.bt[0], [0, 120, 240, 480]);
});
