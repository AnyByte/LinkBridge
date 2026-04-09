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

START_TIMEOUT_SECONDS = 5.0


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
        # Reset readiness so a previous lifecycle's signal can't satisfy this start.
        self._ready.clear()
        self._thread = threading.Thread(
            target=self._run, name="LinkBridge-Link", daemon=True
        )
        self._thread.start()
        if not self._ready.wait(timeout=START_TIMEOUT_SECONDS):
            log.error(
                "link monitor did not become ready within %.1f s — proceeding anyway",
                START_TIMEOUT_SECONDS,
            )
        else:
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
        try:
            loop.call_soon_threadsafe(_shutdown)
        except RuntimeError as e:
            # Loop is already closed (e.g. stop() called twice). Nothing to do.
            log.debug("stop() called on closed loop: %s", e)
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        # Clear references so a subsequent start() can run cleanly.
        self._loop = None
        self._thread = None
        self._link = None
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
        # Guard against non-positive BPM — set_bpm raises on <= 0, and we must
        # never let exceptions escape back into aalink's C++ callback dispatcher.
        if bpm <= 0.0:
            log.warning("link delivered non-positive BPM %.4f, ignoring", bpm)
            return
        try:
            with self.state.lock:
                self.state.set_bpm(float(bpm))
        except Exception as e:
            log.warning("tempo callback failed: %s", e)
            return
        log.debug("link tempo -> %.2f", bpm)

    def _on_transport(self, playing: bool) -> None:
        try:
            with self.state.lock:
                self.state.is_playing = bool(playing)
        except Exception as e:
            log.warning("transport callback failed: %s", e)
            return
        log.info("link transport -> %s", "PLAY" if playing else "STOP")
