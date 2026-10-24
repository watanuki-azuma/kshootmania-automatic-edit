"""Pulse, chart-time, audio-time, and measure conversions (240 pulses/beat)."""

from bisect import bisect_right
import math


class TimingMap:
    def __init__(self, beat):
        bpms = beat["bpm"]
        if not bpms or bpms[0][0] != 0:
            raise ValueError("BPM events must start at pulse zero")
        self._pulses, self._seconds, self._bpms = [], [], []
        seconds, previous_y, previous_bpm = 0.0, 0, bpms[0][1]
        for y, bpm in bpms:
            if y < previous_y or not math.isfinite(bpm) or bpm <= 0:
                raise ValueError("BPM events must be ordered and have positive finite BPMs")
            seconds += (y - previous_y) * 60 / (240 * previous_bpm)
            self._pulses.append(y)
            self._seconds.append(seconds)
            self._bpms.append(bpm)
            previous_y, previous_bpm = y, bpm
        signatures = beat.get("time_sig", [[0, [4, 4]]])
        if not signatures or signatures[0][0] != 0:
            signatures = [[0, [4, 4]], *signatures]
        self._measures, self._measure_pulses, self._lengths = [], [], []
        pulse, previous_idx, previous_length = 0, 0, 960
        for idx, (n, d) in signatures:
            if idx < previous_idx or n <= 0 or d <= 0:
                raise ValueError("Time signatures must be ordered and positive")
            pulse += (idx - previous_idx) * previous_length
            self._measures.append(idx)
            self._measure_pulses.append(pulse)
            self._lengths.append(960 * n / d)
            previous_idx, previous_length = idx, self._lengths[-1]

    def pulse_to_sec(self, pulse):
        """Chart seconds from pulse zero; scroll stops do not stop music time."""
        i = max(0, bisect_right(self._pulses, pulse) - 1)
        return self._seconds[i] + (pulse - self._pulses[i]) * 60 / (240 * self._bpms[i])

    def sec_to_pulse(self, seconds):
        """Return a fractional pulse, preserving sub-pulse audio precision."""
        i = max(0, bisect_right(self._seconds, seconds) - 1)
        return self._pulses[i] + (seconds - self._seconds[i]) * 240 * self._bpms[i] / 60

    def measure_to_pulse(self, measure_idx, offset=0):
        """Convert a zero-based measure index and an offset in pulses."""
        i = max(0, bisect_right(self._measures, measure_idx) - 1)
        return self._measure_pulses[i] + (measure_idx - self._measures[i]) * self._lengths[i] + offset

    def pulse_to_measure(self, pulse):
        """Return (zero-based measure index, offset in pulses)."""
        i = max(0, bisect_right(self._measure_pulses, pulse) - 1)
        count, offset = divmod(pulse - self._measure_pulses[i], self._lengths[i])
        return self._measures[i] + int(count), offset

    def pulse_to_audio_sec(self, pulse, audio):
        """Audio file position = chart time + audio.bgm.offset / 1000.

        Per KSON, a positive offset is the starting point inside the audio file:
        pulse zero at offset=500 corresponds to audio position 0.5 seconds.
        Pass the chart's audio dictionary (or omit bgm for an offset of zero).
        """
        return self.pulse_to_sec(pulse) + audio.get("bgm", {}).get("offset", 0) / 1000

    def audio_sec_to_pulse(self, seconds, audio):
        return self.sec_to_pulse(seconds - audio.get("bgm", {}).get("offset", 0) / 1000)
