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
