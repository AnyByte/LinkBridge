"""Tests for linkbridge.clock_engine."""

import threading
import time

import pytest

from linkbridge.clock_engine import ClockEngine, ClockState


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


def test_set_bpm_rejects_non_positive():
    s = ClockState(lock=threading.Lock())
    with pytest.raises(ValueError, match="must be positive"):
        s.set_bpm(0.0)
    with pytest.raises(ValueError, match="must be positive"):
        s.set_bpm(-60.0)


# ------------------------------------------------------------
# Fixtures for fake time and fake MIDI sink
# ------------------------------------------------------------

class FakeClock:
    """Monotonic-like clock you can advance manually."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, dt: float) -> None:
        self.now += dt


class FakeSleeper:
    """Sleep stand-in that advances a FakeClock instead of blocking."""

    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock
        self.calls: list[float] = []

    def __call__(self, dt: float) -> None:
        self.calls.append(dt)
        if dt > 0:
            self.clock.advance(dt)


class FakeSink:
    """Stand-in for a mido output port that records sent message types."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.closed: bool = False
        self.fail_with: Exception | None = None

    def send(self, msg) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.sent.append(msg.type)

    def close(self) -> None:
        self.closed = True


def _make_state(sink: FakeSink | None, bpm: float = 120.0, is_playing: bool = False,
                start_stop_enabled: bool = False) -> ClockState:
    s = ClockState(lock=threading.Lock())
    s.set_bpm(bpm)
    s.is_playing = is_playing
    s.start_stop_enabled = start_stop_enabled
    s.midi_out = sink
    return s


def test_tick_once_sends_clock_message_to_sink():
    clock = FakeClock()
    sleeper = FakeSleeper(clock)
    sink = FakeSink()
    state = _make_state(sink)
    engine = ClockEngine(state, clock=clock, sleeper=sleeper)
    engine._next_tick_time = clock()

    engine._tick_once()
    engine._tick_once()
    engine._tick_once()

    assert sink.sent == ["clock", "clock", "clock"]


def test_tick_cadence_matches_bpm():
    # At 120 BPM with 24 ppqn, tick interval is 1 / (120/60 * 24) = 1/48 s ≈ 20.833 ms
    clock = FakeClock()
    sleeper = FakeSleeper(clock)
    sink = FakeSink()
    state = _make_state(sink, bpm=120.0)
    engine = ClockEngine(state, clock=clock, sleeper=sleeper)
    engine._next_tick_time = clock()

    for _ in range(48):
        engine._tick_once()

    # 48 ticks at 120 BPM = 1 second of wall-clock time
    assert abs(clock() - 1.0) < 1e-9
    assert sink.sent == ["clock"] * 48


def test_tempo_change_mid_run_applies_on_next_tick():
    clock = FakeClock()
    sleeper = FakeSleeper(clock)
    sink = FakeSink()
    state = _make_state(sink, bpm=120.0)
    engine = ClockEngine(state, clock=clock, sleeper=sleeper)
    engine._next_tick_time = clock()

    # First tick at 120 BPM — expected interval 1/48 s
    engine._tick_once()
    t_after_first = clock()

    # Change BPM to 240 — expected interval halves (1/96 s)
    with state.lock:
        state.set_bpm(240.0)

    engine._tick_once()
    delta = clock() - t_after_first

    assert abs(delta - (1.0 / (240.0 / 60.0 * 24))) < 1e-12


def test_transport_start_emitted_before_next_clock_when_toggle_on():
    clock = FakeClock()
    sleeper = FakeSleeper(clock)
    sink = FakeSink()
    state = _make_state(sink, is_playing=False, start_stop_enabled=True)
    engine = ClockEngine(state, clock=clock, sleeper=sleeper)
    engine._next_tick_time = clock()

    # First tick: not playing. Only clock.
    engine._tick_once()
    assert sink.sent == ["clock"]

    # Transport goes True
    with state.lock:
        state.is_playing = True

    engine._tick_once()
    # Expect START emitted before the CLOCK tick
    assert sink.sent == ["clock", "start", "clock"]

    # Next tick should not re-emit START
    engine._tick_once()
    assert sink.sent == ["clock", "start", "clock", "clock"]


def test_transport_stop_emitted_before_next_clock_when_toggle_on():
    clock = FakeClock()
    sleeper = FakeSleeper(clock)
    sink = FakeSink()
    state = _make_state(sink, is_playing=True, start_stop_enabled=True)
    engine = ClockEngine(state, clock=clock, sleeper=sleeper)
    engine._next_tick_time = clock()
    engine._prev_is_playing = True  # already playing before first tick

    engine._tick_once()
    assert sink.sent == ["clock"]

    with state.lock:
        state.is_playing = False

    engine._tick_once()
    assert sink.sent == ["clock", "stop", "clock"]


def test_transport_transitions_do_not_emit_start_stop_when_toggle_off():
    clock = FakeClock()
    sleeper = FakeSleeper(clock)
    sink = FakeSink()
    state = _make_state(sink, is_playing=False, start_stop_enabled=False)
    engine = ClockEngine(state, clock=clock, sleeper=sleeper)
    engine._next_tick_time = clock()

    engine._tick_once()
    with state.lock:
        state.is_playing = True
    engine._tick_once()
    with state.lock:
        state.is_playing = False
    engine._tick_once()

    # Only clock ticks — no start/stop ever.
    assert sink.sent == ["clock", "clock", "clock"]


def test_tick_once_with_no_device_does_not_raise():
    clock = FakeClock()
    sleeper = FakeSleeper(clock)
    state = _make_state(sink=None)  # midi_out = None
    engine = ClockEngine(state, clock=clock, sleeper=sleeper)
    engine._next_tick_time = clock()

    # Should not raise and should still advance timing.
    engine._tick_once()
    engine._tick_once()
    assert clock() > 0


def test_send_failure_nulls_midi_out_and_keeps_running():
    clock = FakeClock()
    sleeper = FakeSleeper(clock)
    sink = FakeSink()
    sink.fail_with = IOError("unplugged")
    state = _make_state(sink)
    engine = ClockEngine(state, clock=clock, sleeper=sleeper)
    engine._next_tick_time = clock()

    engine._tick_once()  # raises internally, caught, drops the port

    with state.lock:
        assert state.midi_out is None

    # Subsequent ticks must not raise even though port is None now.
    engine._tick_once()
    engine._tick_once()


def test_transport_send_failure_nulls_midi_out_and_skips_clock():
    clock = FakeClock()
    sleeper = FakeSleeper(clock)
    sink = FakeSink()
    sink.fail_with = IOError("unplugged")
    state = _make_state(sink, is_playing=True, start_stop_enabled=True)
    engine = ClockEngine(state, clock=clock, sleeper=sleeper)
    engine._next_tick_time = clock()
    engine._prev_is_playing = False  # forces transport edge on first tick

    engine._tick_once()  # transport send raises, port is dropped, clock skipped

    with state.lock:
        assert state.midi_out is None
    # The failing send was attempted but never recorded by FakeSink.
    assert sink.sent == []
    # Subsequent ticks must not raise (port is None).
    engine._tick_once()


def test_start_and_stop_real_thread_streams_clock():
    sink = FakeSink()
    state = _make_state(sink, bpm=240.0)  # fast so the test is quick
    engine = ClockEngine(state)
    engine.start()
    time.sleep(0.1)  # ~9-10 ticks at 240 BPM
    engine.stop()

    # We can't assert an exact count, but there should be SOMETHING and no crashes.
    assert "clock" in sink.sent
    assert not state.clock_crashed
    assert sink.closed is True
    assert state.midi_out is None


def test_run_sets_clock_crashed_on_unhandled_exception():
    state = _make_state(sink=None)
    engine = ClockEngine(state)

    # Force _tick_once to explode on first call.
    def boom():
        raise RuntimeError("simulated")
    engine._tick_once = boom  # type: ignore[assignment]

    engine._running.set()
    engine._run()  # runs on current thread until exception

    with state.lock:
        assert state.clock_crashed is True
