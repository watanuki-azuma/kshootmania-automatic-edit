import {bounds, button, entries, key, values} from './chartops.js';

export class Highway {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.scroll = 0;
    this.scale = 0.3;
    this.selection = [];
    this.gesture = null;
    this.playhead = 0;
    this.onsets = [];
    this.showOnsets = false;
  }
  resize() {
    const {width, height} = this.canvas.getBoundingClientRect();
    const ratio = window.devicePixelRatio || 1;
    this.canvas.width = Math.round(width * ratio);
    this.canvas.height = Math.round(height * ratio);
    this.ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    this.w = width; this.h = height;
    this.inner = Math.min(400, Math.max(160, width - 200));
    this.left = (width - this.inner) / 2;
    this.outerLeft = this.left - 40;
    this.outerWidth = this.inner + 80;
  }
  y(pulse) { return this.h - 36 - (pulse - this.scroll) * this.scale; }
  pulse(y) { return this.scroll + (this.h - 36 - y) / this.scale; }
  laserX(value, width = 1) {
    return width === 2 ? this.outerLeft + value * this.outerWidth : this.left - 15 + value * (this.inner + 30);
  }
  laserValue(x, width = 1) {
    return width === 2 ? (x - this.outerLeft) / this.outerWidth : (x - this.left + 15) / (this.inner + 30);
  }
  lane(x, kind) {
    if (x < this.left || x >= this.left + this.inner) return -1;
    return Math.floor((x - this.left) / (this.inner / (kind === 'bt' ? 4 : 2)));
  }
  pointAt(x, y, side) {
    let best = null, distance = 12;
    (this.chart.note?.laser?.[side] || []).forEach(([start, points, width], section) => {
      points.forEach(([ry, v], point) => {
        values(v).forEach((value, endpoint) => {
          const d = Math.hypot(x - this.laserX(value, width || 1), y - this.y(start + ry));
          if (d < distance) { distance = d; best = {section, point, endpoint, width: width || 1}; }
        });
      });
    });
    return best;
  }
  inRectangle(ref, x0, x1) {
    let left, right;
    if (ref.kind === 'laser') {
      const xs = ref.note[1].flatMap(p => values(p[1]).map(v => this.laserX(v, ref.note[2] || 1)));
      left = Math.min(...xs); right = Math.max(...xs);
    } else {
      const width = this.inner / (ref.kind === 'bt' ? 4 : 2);
      left = this.left + ref.lane * width; right = left + width;
    }
    return right >= Math.min(x0, x1) && left <= Math.max(x0, x1);
  }
  draw() {
    if (!this.chart || !this.w) return;
    const c = this.ctx, {w, h, left, inner} = this;
    const selected = new Set(this.selection.map(key));
    const line = (x0, y0, x1, y1, color, width = 1) => {
      c.strokeStyle = color; c.lineWidth = width; c.beginPath(); c.moveTo(x0, y0); c.lineTo(x1, y1); c.stroke();
    };
    c.clearRect(0, 0, w, h);
    c.fillStyle = '#0c101a'; c.fillRect(0, 0, w, h);
    c.fillStyle = '#1b2232'; c.fillRect(left, 0, inner, h);
    c.fillStyle = '#151b28'; c.fillRect(left, 0, inner / 4, h); c.fillRect(left + inner / 2, 0, inner / 4, h);
    for (let i = 0; i <= 4; i++) line(left + i * inner / 4, 0, left + i * inner / 4, h, '#343d52');
    const min = Math.max(0, this.pulse(h)), max = this.pulse(0);
    const first = Math.max(0, this.timing.pulseToMeasure(min)[0]);
    const last = this.timing.pulseToMeasure(max)[0] + 1;
    c.font = '12px ui-monospace, monospace';
    // Extremely short signatures can produce many lines; cap drawing to screen resolution.
    for (let m = first, count = 0; m <= last && count < 3000; m++, count++) {
      const start = this.timing.measureToPulse(m), next = this.timing.measureToPulse(m + 1);
      const [, den] = this.timing.signatureAt(m), beat = 960 / den;
      for (let p = start + beat; p < next; p += beat) {
        if (beat * this.scale < 3) break;
        line(left, this.y(p), left + inner, this.y(p), '#353e50');
      }
      if (this.grid) for (let d = 1; d < this.grid; d++) {
        const p = start + (next - start) * d / this.grid;
        line(left, this.y(p), left + inner, this.y(p), '#ffffff09');
      }
      line(this.outerLeft - 6, this.y(start), this.outerLeft + this.outerWidth + 6, this.y(start), '#72819b');
      c.fillStyle = '#aebbd0'; c.fillText(`m${m}`, Math.max(8, this.outerLeft - 57), this.y(start) - 5);
    }
    if (this.showOnsets) for (const [p, strength] of this.onsets) {
      if (p >= min && p <= max) line(left + inner + 47, this.y(p), left + inner + 52 + strength * 18, this.y(p), '#b4c6e566', 2);
    }
    const all = entries(this.chart);
    for (const kind of ['fx', 'bt']) for (const ref of all) {
      if (ref.kind !== kind) continue;
      const [start, end] = bounds(kind, ref.note);
      if (end < min || start > max) continue;
      const [, length] = button(ref.note), width = inner / (kind === 'bt' ? 4 : 2);
      const x = left + ref.lane * width, pad = kind === 'bt' ? 6 : 3;
      const y0 = this.y(start), y1 = this.y(end);
      c.fillStyle = kind === 'bt' ? (length ? '#d6e0f0cf' : '#eff7ff') : (length ? '#c47a29a0' : '#ffa544');
      c.fillRect(x + pad, y1 - 5, width - pad * 2, y0 - y1 + 5);
      if (selected.has(key(ref))) {
        c.strokeStyle = '#ffe180'; c.lineWidth = 2;
        c.strokeRect(x + pad - 2, y1 - 7, width - pad * 2 + 4, y0 - y1 + 9);
      }
    }
    for (const ref of all) {
      if (ref.kind !== 'laser') continue;
      const [start, points, width = 1] = ref.note;
      const [a, b] = bounds('laser', ref.note);
      if (b < min || a > max) continue;
      const color = ref.lane ? '#ff63bf' : '#37d6f5';
      c.strokeStyle = selected.has(key(ref)) ? '#ffe180' : color;
      c.lineWidth = 5; c.lineJoin = 'round';
      for (let i = 0; i < points.length; i++) {
        const [ry, v, curve = [0, 0]] = points[i], [before, after] = values(v), y = this.y(start + ry);
        const x0 = this.laserX(before, width), x1 = this.laserX(after, width);
        if (before !== after) {
          c.fillStyle = color; c.fillRect(Math.min(x0, x1) - 2, y - 5, Math.abs(x1 - x0) + 4, 10);
        }
        if (i + 1 < points.length) {
          const [nextRy, nextV] = points[i + 1];
          const nx = this.laserX(values(nextV)[0], width), ny = this.y(start + nextRy);
          c.beginPath(); c.moveTo(x1, y);
          c.quadraticCurveTo(x1 + (nx - x1) * curve[1], y + (ny - y) * curve[0], nx, ny);
          c.stroke();
        }
        for (const x of [x0, x1]) {
          c.fillStyle = '#101828'; c.fillRect(x - 4, y - 4, 8, 8);
          c.strokeStyle = selected.has(key(ref)) ? '#ffe180' : color; c.lineWidth = 1.5;
          c.strokeRect(x - 4, y - 4, 8, 8); c.lineWidth = 5;
        }
      }
    }
    // Lane labels under the judgment area, aligned with the lanes.
    c.fillStyle = '#0c101acc'; c.fillRect(0, h - 22, w, 22);
    c.textAlign = 'center';
    ['A', 'B', 'C', 'D'].forEach((name, i) => { c.fillStyle = '#aebbd0'; c.fillText(name, left + (i + 0.5) * inner / 4, h - 7); });
    c.fillStyle = '#37d6f5'; c.fillText('L', left - 24, h - 7);
    c.fillStyle = '#ff63bf'; c.fillText('R', left + inner + 24, h - 7);
    c.textAlign = 'start';
    const py = this.y(this.playhead);
    line(this.outerLeft - 12, py, this.outerLeft + this.outerWidth + 12, py, '#a5ffc7', 2);
    c.fillStyle = '#a5ffc7'; c.fillText('▶', this.outerLeft - 28, py + 4);
    const g = this.gesture;
    if (g?.type === 'select') {
      const x = Math.min(g.x, g.currentX), y = Math.min(this.y(g.pulse), this.y(g.current));
      const width = Math.abs(g.x - g.currentX), height = Math.abs(this.y(g.pulse) - this.y(g.current));
      c.fillStyle = '#7bb5ff22'; c.fillRect(x, y, width, height);
      c.strokeStyle = '#a5caff'; c.lineWidth = 1; c.strokeRect(x, y, width, height);
    } else if (g?.type === 'button') {
      const width = inner / (g.kind === 'bt' ? 4 : 2);
      c.fillStyle = '#ffe18088';
      c.fillRect(left + width * g.lane + 3, this.y(Math.max(g.pulse, g.current)) - 5,
        width - 6, Math.abs(g.current - g.pulse) * this.scale + 5);
    }
    this.canvas.dataset.drawn = 'true';
  }
}
