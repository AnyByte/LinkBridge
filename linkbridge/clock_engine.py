"""Shared clock state + the 24 ppqn MIDI clock tick generator."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field

import mido

log = logging.getLogger(__name__)

PPQN = 24  # MIDI clock pulses per quarter note (fixed by MIDI spec)


def _interval_for_bpm(bpm: float) -> float:
    """Return seconds-per-tick for a given BPM at 24 ppqn."""
    return 1.0 / (bpm / 60.0 * PPQN)


@dataclass
class ClockState:
    lock: threading.Lock
    bpm: float = 120.0
    tick_interval: float = field(default_factory=lambda: _interval_for_bpm(120.0))
    is_playing: bool = False
    start_stop_enabled: bool = False
    midi_out: mido.ports.BaseOutput | None = None
    clock_crashed: bool = False

    def set_bpm(self, bpm: float) -> None:
        """Update bpm and recompute tick_interval. Caller must hold the lock."""
        if bpm <= 0.0:
            raise ValueError(f"BPM must be positive, got {bpm!r}")
        self.bpm = bpm
        self.tick_interval = _interval_for_bpm(bpm)


class ClockEngine:
    """Runs a 24 ppqn MIDI clock tick loop on a dedicated thread.

    Tests can drive `_tick_once()` directly with a FakeClock / FakeSleeper /
    FakeSink — no real threads or real time involved.
    """

    def __init__(
        self,
        state: ClockState,
        clock=None,
        sleeper=None,
    ) -> None:
        import time as _time
        self.state = state
        self._clock = clock or _time.monotonic
        self._sleeper = sleeper or _time.sleep
        self._running = False
        self._thread: threading.Thread | None = None
        self._next_tick_time: float = 0.0
        self._prev_is_playing: bool = False

    # ----- test-facing single-iteration method -----

    def _tick_once(self) -> None:
        # Snapshot state under the lock — keep the critical section tiny.
        with self.state.lock:
            interval = self.state.tick_interval
            is_playing = self.state.is_playing
            start_stop_enabled = self.state.start_stop_enabled
            port = self.state.midi_out

        # Detect transport transition (runs regardless of toggle — we still
        # need to update _prev_is_playing so we don't fire a stale edge later).
        transport_edge = is_playing != self._prev_is_playing
        if transport_edge:
            self._prev_is_playing = is_playing
            if start_stop_enabled and port is not None:
                msg_type = "start" if is_playing else "stop"
                try:
                    port.send(mido.Message(msg_type))
                    log.info("sent MIDI %s", msg_type.upper())
                except Exception as e:
                    log.warning("transport send failed, dropping device: %s", e)
                    with self.state.lock:
                        if self.state.midi_out is port:
                            self.state.midi_out = None
                    port = None  # skip the clock tick below

        # Clock tick (always emitted when a port is still set)
        if port is not None:
            try:
                port.send(mido.Message("clock"))
            except Exception as e:
                log.warning("clock send failed, dropping device: %s", e)
                with self.state.lock:
                    if self.state.midi_out is port:
                        self.state.midi_out = None

        # Timing bookkeeping
        self._next_tick_time += interval
        sleep_time = self._next_tick_time - self._clock()
        if sleep_time > 0:
            self._sleeper(sleep_time)
        elif sleep_time < -interval:
            self._next_tick_time = self._clock()

    # ----- thread lifecycle -----

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._running = True
        self._next_tick_time = self._clock()
        self._prev_is_playing = False
        self._thread = threading.Thread(
            target=self._run, name="LinkBridge-Clock", daemon=True
        )
        self._thread.start()
        log.info("clock thread started")

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        # Final cleanup: if transport was playing and toggle is on, send STOP.
        with self.state.lock:
            port = self.state.midi_out
            should_send_stop = (
                self.state.start_stop_enabled and self.state.is_playing and port is not None
            )
        if should_send_stop:
            try:
                port.send(mido.Message("stop"))
                log.info("sent final MIDI STOP on shutdown")
            except Exception as e:
                log.warning("final stop send failed: %s", e)
        # Close and release the port.
        with self.state.lock:
            port = self.state.midi_out
            self.state.midi_out = None
        if port is not None:
            try:
                port.close()
            except Exception as e:
                log.warning("port close failed: %s", e)
        log.info("clock thread stopped")

    def _run(self) -> None:
        try:
            while self._running:
                self._tick_once()
        except Exception:
            log.exception("clock thread crashed")
            with self.state.lock:
                self.state.clock_crashed = True
