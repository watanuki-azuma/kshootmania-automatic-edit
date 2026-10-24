import pytest

from ksmauto.timing import TimingMap


def test_bpm_changes_and_inverse():
    timing = TimingMap({"bpm": [[0, 120], [960, 240], [1920, 60]]})
    assert [timing.pulse_to_sec(p) for p in (0, 240, 960, 1440, 1920, 2160)] == [0, 0.5, 2, 2.5, 3, 4]
    for pulse in (-240, 0, 12.25, 959.99, 960, 1920, 12345):
        assert timing.sec_to_pulse(timing.pulse_to_sec(pulse)) == pytest.approx(pulse)


def test_signature_changes_and_inverse():
    timing = TimingMap({"bpm": [[0, 120]], "time_sig": [[0, [4, 4]], [2, [3, 4]], [4, [7, 8]]]})
    assert [timing.measure_to_pulse(m) for m in range(7)] == [0, 960, 1920, 2640, 3360, 4200, 5040]
    assert timing.pulse_to_measure(1919) == (1, 959)
    assert timing.pulse_to_measure(1920) == (2, 0)
    assert timing.pulse_to_measure(3360) == (4, 0)
    assert timing.pulse_to_measure(4300) == (5, 100)
    for pulse in (-20, 0, 10.5, 960, 2000, 3500, 10000):
        assert timing.measure_to_pulse(*timing.pulse_to_measure(pulse)) == pytest.approx(pulse)


@pytest.mark.parametrize("offset", [-500, 0, 500])
def test_audio_offset_sign_and_inverse(offset):
    timing = TimingMap({"bpm": [[0, 120]]})
    audio = {"bgm": {"offset": offset}}
    assert timing.pulse_to_audio_sec(0, audio) == offset / 1000
    assert timing.pulse_to_audio_sec(240, audio) == 0.5 + offset / 1000
    assert timing.audio_sec_to_pulse(offset / 1000, audio) == 0
    assert timing.pulse_to_audio_sec(240, {}) == 0.5


def test_scroll_stops_do_not_stop_chart_clock():
    timing = TimingMap({"bpm": [[0, 120]], "stop": [[0, 960]], "scroll_speed": [[0, 0]]})
    assert timing.pulse_to_sec(960) == 2


@pytest.mark.parametrize("bpms", [[], [[240, 120]], [[0, 0]], [[0, -120]], [[0, float("inf")]], [[0, 120], [240, 120], [120, 120]]])
def test_invalid_bpm_map(bpms):
    with pytest.raises(ValueError):
        TimingMap({"bpm": bpms})
