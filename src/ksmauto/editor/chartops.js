// Pure, immutable chart operations. References are {kind, lane, index}.
export const clone = value => JSON.parse(JSON.stringify(value));
export const button = n => typeof n === 'number' ? [n, 0] : n;
export const values = v => Array.isArray(v) ? v : [v, v];
export const key = ref => `${ref.kind}:${ref.lane}:${ref.index}`;
export const quantize = v => Math.round(Math.max(0, Math.min(1, v)) * 50) / 50;
export function bounds(kind, n) {
  if (kind === 'laser') return [n[0], n[0] + n[1].at(-1)[0]];
  const [p, len] = button(n);
  return [p, p + len];
}
export function entries(chart) {
  const result = [];
  for (const kind of ['bt', 'fx', 'laser'])
    (chart.note?.[kind] || []).forEach((lane, l) => lane.forEach((note, i) =>
      result.push({kind, lane: l, index: i, note})));
  return result;
}
function prepare(chart) {
  const result = clone(chart);
  result.note ||= {};
  for (const [kind, count] of [['bt', 4], ['fx', 2], ['laser', 2]])
    result.note[kind] ||= Array.from({length: count}, () => []);
  return result;
}
export function checkOverlaps(chart) {
  for (const kind of ['bt', 'fx', 'laser']) {
    for (const lane of chart.note?.[kind] || []) {
      const ordered = [...lane].sort((a, b) => bounds(kind, a)[0] - bounds(kind, b)[0]);
      let previousStart = -1, previousEnd = -1;
      for (const note of ordered) {
        const [start, end] = bounds(kind, note);
        if (start < 0 || !Number.isInteger(start) || !Number.isInteger(end))
          throw new Error('Notes must use nonnegative integer pulses.');
        if (start < previousEnd || start === previousStart)
          throw new Error(`Edit rejected: notes overlap on the same ${kind.toUpperCase()} lane.`);
        previousStart = start; previousEnd = end;
      }
    }
  }
  return chart;
}
function finish(chart) {
  for (const kind of ['bt', 'fx', 'laser'])
    for (const lane of chart.note[kind]) lane.sort((a, b) => bounds(kind, a)[0] - bounds(kind, b)[0]);
  return checkOverlaps(chart);
}
export function toggleButton(chart, kind, lane, a, b = a) {
  const result = prepare(chart), notes = result.note[kind][lane];
  const start = Math.min(a, b), length = Math.abs(b - a);
  const existing = notes.findIndex(n => button(n)[0] === start);
  if (!length && existing >= 0) notes.splice(existing, 1);
  else notes.push(length ? [start, length] : start);
  return finish(result);
}
export function deleteSelection(chart, refs) {
  const selected = new Set(refs.map(key));
  const result = prepare(chart);
  for (const kind of ['bt', 'fx', 'laser'])
    result.note[kind] = result.note[kind].map((lane, l) => lane.filter((_, i) =>
      !selected.has(key({kind, lane: l, index: i}))));
  return result;
}
export function copySelection(chart, refs, sourcePulse) {
  return {sourcePulse, notes: refs.map(ref => ({kind: ref.kind, lane: ref.lane,
    note: clone(chart.note[ref.kind][ref.lane][ref.index])}))};
}
export function pasteSelection(chart, clipboard, targetPulse) {
  const result = prepare(chart), delta = targetPulse - clipboard.sourcePulse;
  for (const {kind, lane, note: source} of clipboard.notes) {
    let note = clone(source);
    if (typeof note === 'number') note += delta;
    else note[0] += delta;
    result.note[kind][lane].push(note);
  }
  return finish(result);
}
export function mirrorSelection(chart, refs) {
  const result = deleteSelection(chart, refs);
  for (const {kind, lane, note: original} of refs.map(ref => ({...ref,
    note: chart.note[ref.kind][ref.lane][ref.index]}))) {
    const note = clone(original), opposite = (kind === 'bt' ? 3 : 1) - lane;
    if (kind === 'laser') for (const point of note[1])
      point[1] = Array.isArray(point[1]) ? point[1].map(v => 1 - v) : 1 - point[1];
    result.note[kind][opposite].push(note);
  }
  return finish(result);
}
export function addLaser(chart, lane, pulse, value, step, width = 1, slam = false) {
  const result = prepare(chart), sections = result.note.laser[lane];
  value = quantize(value);
  const section = [...sections].reverse().find(s => {
    const end = bounds('laser', s)[1];
    return (s[2] || 1) === width && pulse >= end && pulse <= end + step + 1;
  });
  if (section) {
    const last = section[1].at(-1), end = section[0] + last[0];
    if (pulse === end) {
      if (!slam) throw new Error('Use Shift+click to create a slam at the last point.');
      last[1] = [values(last[1])[0], value];
    } else section[1].push([pulse - section[0], value]);
  } else sections.push([pulse, [[0, value]], width]);
  return finish(result);
}
export function moveLaserPoint(chart, lane, sectionIndex, pointIndex, value, endpoint = 0) {
  const result = prepare(chart), point = result.note.laser[lane][sectionIndex][1][pointIndex];
  value = quantize(value);
  if (Array.isArray(point[1])) point[1][endpoint] = value;
  else point[1] = value;
  return result;
}
export function deleteLaserPoint(chart, lane, sectionIndex, pointIndex) {
  const result = prepare(chart), sections = result.note.laser[lane], section = sections[sectionIndex];
  section[1].splice(pointIndex, 1);
  if (!section[1].length) sections.splice(sectionIndex, 1);
  else {
    const delta = section[1][0][0];
    section[0] += delta;
    for (const point of section[1]) point[0] -= delta;
  }
  return result;
}
export function selectRange(chart, start, end, lanePredicate = () => true) {
  [start, end] = [Math.min(start, end), Math.max(start, end)];
  return entries(chart).filter(ref => {
    const [a, b] = bounds(ref.kind, ref.note);
    return a <= end && b >= start && lanePredicate(ref);
  }).map(({kind, lane, index}) => ({kind, lane, index}));
}
export function history(initial, limit = 100) {
  let states = [clone(initial)], cursor = 0;
  return {
    push(chart) {
      if (JSON.stringify(states[cursor]) === JSON.stringify(chart)) return false;
      states = states.slice(0, cursor + 1);
      states.push(clone(chart));
      if (states.length > limit) states.shift();
      cursor = states.length - 1;
      return true;
    },
    undo() { cursor = Math.max(0, cursor - 1); return clone(states[cursor]); },
    redo() { cursor = Math.min(states.length - 1, cursor + 1); return clone(states[cursor]); },
  };
}
