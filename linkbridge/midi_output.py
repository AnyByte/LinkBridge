"""Thin wrappers around mido's CoreMIDI output port APIs."""

from __future__ import annotations

import logging

import mido

log = logging.getLogger(__name__)


def list_outputs() -> list[str]:
    """Return the list of available CoreMIDI output port names."""
    return list(mido.get_output_names())


def open_output(name: str) -> mido.ports.BaseOutput:
    """Open and return a mido output port by name. Raises on failure."""
    port = mido.open_output(name)
    log.info("opened MIDI output: %s", name)
    return port
