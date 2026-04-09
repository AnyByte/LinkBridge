"""Ableton Link monitor thread backed by aalink.

Runs an asyncio loop in a dedicated daemon thread. Registers reactive
callbacks on the Link object so tempo and transport updates flow into
`ClockState` without any polling.
"""

from __future__ import annotations

import asyncio
import logging
import threading

from aalink import Link

from linkbridge.clock_engine import ClockState

log = logging.getLogger(__name__)


class LinkMonitor:
    def __init__(self, state: ClockState, initial_bpm: float = 120.0, quantum: float = 4.0) -> None:
        self.state = state
        self.initial_bpm = initial_bpm
        self.quantum = quantum
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._link: Link | None = None
        self._ready = threading.Event()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run, name="LinkBridge-Link", daemon=True
        )
        self._thread.start()
        self._ready.wait(timeout=5.0)
        log.info("link monitor started")

    def stop(self) -> None:
        loop = self._loop
        if loop is None:
            return
        # Disable link then stop the loop from within itself.
        def _shutdown() -> None:
            try:
                if self._link is not None:
                    self._link.enabled = False
            except Exception as e:
                log.warning("link disable failed: %s", e)
            loop.stop()
        loop.call_soon_threadsafe(_shutdown)
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        log.info("link monitor stopped")

    # ----- internals -----

    def _run(self) -> None:
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self._async_setup())
            self._loop.run_forever()
        except Exception:
            log.exception("link thread crashed")
            self._ready.set()
        finally:
            try:
                if self._loop is not None and not self._loop.is_closed():
                    self._loop.close()
            except Exception:
                pass
            log.info("link thread exited")

    async def _async_setup(self) -> None:
        self._link = Link(self.initial_bpm)
        self._link.quantum = self.quantum
        self._link.start_stop_sync_enabled = True
        self._link.set_tempo_callback(self._on_tempo)
        self._link.set_start_stop_callback(self._on_transport)
        self._link.enabled = True
        self._ready.set()

    def _on_tempo(self, bpm: float) -> None:
        with self.state.lock:
            self.state.set_bpm(float(bpm))
        log.debug("link tempo -> %.2f", bpm)

    def _on_transport(self, playing: bool) -> None:
        with self.state.lock:
            self.state.is_playing = bool(playing)
        log.info("link transport -> %s", "PLAY" if playing else "STOP")
