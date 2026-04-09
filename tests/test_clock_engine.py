"""Tests for linkbridge.clock_engine."""

import threading

from linkbridge.clock_engine import ClockState


def test_clock_state_defaults():
    s = ClockState(lock=threading.Lock())
    assert s.bpm == 120.0
    assert abs(s.tick_interval - (1.0 / (120.0 / 60.0 * 24))) < 1e-12
    assert s.is_playing is False
    assert s.start_stop_enabled is False
    assert s.midi_out is None
    assert s.clock_crashed is False


def test_set_bpm_recomputes_tick_interval():
    s = ClockState(lock=threading.Lock())
    s.set_bpm(140.0)
    assert s.bpm == 140.0
    expected = 1.0 / (140.0 / 60.0 * 24)
    assert abs(s.tick_interval - expected) < 1e-12
