// Audio is the playback clock; performance.now is used for silent preview/pre-roll.
export class Playback {
  constructor(audio, available) {
    this.audio = audio;
    this.available = available;
    this.playing = false;
    this.rate = 1;
    this.position = 0;
    this.context = null;
    this.oscillators = new Set();
    this.scheduledUntil = null;
    this.generation = 0;
  }
  chartTime() {
    if (!this.playing) return this.timing.pulseToSec(this.position);
    const virtual = this.startTime + (performance.now() - this.started) / 1000 * this.rate;
    if (this.available && this.audioStarted) return this.audio.currentTime - this.offset / 1000;
    return virtual;
  }
  pulse() { return this.playing ? this.timing.secToPulse(this.chartTime()) : this.position; }
  configure(chart, timing) {
    this.timing = timing;
    this.offset = chart.audio?.bgm?.offset || 0;
  }
  clearTicks() {
    for (const oscillator of this.oscillators) oscillator.stop();
    this.oscillators.clear(); this.scheduledUntil = null;
  }
  async play() {
    if (this.playing) return;
    this.startTime = this.timing.pulseToSec(this.position);
    this.started = performance.now();
    this.audioStarted = false;
    this.generation++;
    this.playing = true;
    if (this.available && this.startTime + this.offset / 1000 >= 0) {
      try { await this.startAudio(this.startTime + this.offset / 1000); }
      catch (error) { this.pause(); throw error; }
    }
  }
  async startAudio(seconds) {
    const generation = this.generation;
    this.startingAudio = true;
    try {
      this.audio.currentTime = Math.max(0, seconds);
      this.audio.playbackRate = this.rate;
      await this.audio.play();
      if (this.playing && generation === this.generation) this.audioStarted = true;
    } catch (error) {
      if (generation === this.generation) throw error;
    } finally {
      if (generation === this.generation) this.startingAudio = false;
    }
  }
  frame() {
    if (this.playing && this.available && !this.audioStarted && !this.startingAudio) {
      const seconds = this.chartTime() + this.offset / 1000;
      if (seconds >= 0) {
        this.startAudio(seconds).catch(error => {
          this.pause(); this.onError?.(error);
        });
      }
    }
  }
  pause() {
    this.position = this.pulse();
    this.playing = false;
    this.generation++; this.startingAudio = false;
    this.audio.pause(); this.clearTicks();
  }
  async seek(pulse) {
    const resume = this.playing;
    this.pause(); this.position = Math.max(0, pulse);
    if (resume) await this.play();
    else if (this.available) this.audio.currentTime = Math.max(0, this.timing.pulseToAudio(this.position));
  }
  async setRate(rate) {
    const resume = this.playing;
    this.pause(); this.rate = rate;
    this.audio.playbackRate = rate;
    if (resume) await this.play();
  }
  async enableSound() {
    this.context ||= new AudioContext();
    await this.context.resume();
    this.scheduledUntil = null;
  }
  tickAt(delay, frequency, volume) {
    if (!this.context) return;
    const t = this.context.currentTime + Math.max(0, delay);
    const oscillator = this.context.createOscillator(), gain = this.context.createGain();
    oscillator.type = 'sine'; oscillator.frequency.value = frequency;
    gain.gain.setValueAtTime(volume, t);
    gain.gain.exponentialRampToValueAtTime(0.001, t + 0.035);
    oscillator.connect(gain); gain.connect(this.context.destination);
    this.oscillators.add(oscillator);
    oscillator.onended = () => { this.oscillators.delete(oscillator); oscillator.disconnect(); gain.disconnect(); };
    oscillator.start(t); oscillator.stop(t + 0.04);
  }
  schedule(events) {
    if (!this.context || !this.playing) return;
    const now = this.chartTime(), end = now + 0.12 * this.rate;
    const start = Math.max(now - 0.03, this.scheduledUntil ?? now - 0.03);
    for (const [sec, frequency, volume] of events)
      if (sec > start && sec <= end) this.tickAt((sec - now) / this.rate, frequency, volume);
    this.scheduledUntil = end;
  }
}
