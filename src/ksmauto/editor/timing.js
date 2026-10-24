// Music time follows BPM, independent of visual scroll speed and stops.
function indexAt(events, value) {
  let lo = 0, hi = events.length;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if (events[mid][0] <= value) lo = mid + 1;
    else hi = mid;
  }
  return Math.max(0, lo - 1);
}

export function timingMap(beat, offset = 0) {
  const bpms = [];
  let seconds = 0, previous = 0, bpm = beat.bpm[0][1];
  for (const [pulse, next] of beat.bpm) {
    seconds += (pulse - previous) * 60 / (240 * bpm);
    bpms.push([pulse, seconds, next]);
    previous = pulse; bpm = next;
  }
  const source = beat.time_sig?.length ? [...beat.time_sig] : [[0, [4, 4]]];
  if (source[0][0] !== 0) source.unshift([0, [4, 4]]);
  const signatures = [];
  let pulse = 0, measure = 0, length = 960;
  for (const [m, [n, d]] of source) {
    pulse += (m - measure) * length;
    length = 960 * n / d;
    signatures.push([m, pulse, length, n, d]);
    measure = m;
  }
  const secondEvents = bpms.map(e => [e[1], ...e]);
  const pulseEvents = signatures.map(e => [e[1], ...e]);
  const pulseToSec = p => {
    const [y, sec, b] = bpms[indexAt(bpms, p)];
    return sec + (p - y) * 60 / (240 * b);
  };
  const secToPulse = s => {
    const [, y, sec, b] = secondEvents[indexAt(secondEvents, s)];
    return y + (s - sec) * 240 * b / 60;
  };
  const measureToPulse = m => {
    const [start, y, len] = signatures[indexAt(signatures, m)];
    return y + (m - start) * len;
  };
  const pulseToMeasure = p => {
    const [, m, y, len] = pulseEvents[indexAt(pulseEvents, p)];
    const count = Math.floor((p - y) / len);
    return [m + count, p - y - count * len];
  };
  const signatureAt = m => signatures[indexAt(signatures, m)].slice(3);
  const snap = (p, divisions) => {
    const [m, within] = pulseToMeasure(Math.max(0, p));
    const start = measureToPulse(m), step = (measureToPulse(m + 1) - start) / divisions;
    return Math.max(0, Math.round(start + Math.round(within / step) * step));
  };
  return {pulseToSec, secToPulse, measureToPulse, pulseToMeasure, signatureAt, snap,
    pulseToAudio: p => pulseToSec(p) + offset / 1000,
    audioToPulse: s => secToPulse(s - offset / 1000)};
}
