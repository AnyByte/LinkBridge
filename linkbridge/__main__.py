"""Entry point for `python -m linkbridge`. Wires modules together and starts the app."""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import threading
from pathlib import Path

import mido

from linkbridge import midi_output
from linkbridge.app import MenuBarApp
from linkbridge.clock_engine import ClockEngine, ClockState
from linkbridge.link_monitor import LinkMonitor
from linkbridge.settings import Settings

LOG_DIR = Path.home() / "Library" / "Logs" / "LinkBridge"
LOG_FILE = LOG_DIR / "linkbridge.log"


def _configure_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if os.environ.get("LINKBRIDGE_DEBUG") == "1" else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)

    # Rotating file handler
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=1 * 1024 * 1024, backupCount=3
    )
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    )
    root.addHandler(file_handler)

    # Console handler — useful when running from source
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))
    root.addHandler(console_handler)


def _resolve_initial_device(settings: Settings) -> mido.ports.BaseOutput | None:
    """Return an opened mido output port, or None if nothing is available."""
    log = logging.getLogger(__name__)
    try:
        available = midi_output.list_outputs()
    except Exception as e:
        log.error("listing MIDI outputs failed at startup: %s", e)
        return None

    if not available:
        log.warning("no MIDI outputs available at startup")
        return None

    if settings.last_device and settings.last_device in available:
        try:
            return midi_output.open_output(settings.last_device)
        except Exception as e:
            log.warning(
                "failed to reopen last device '%s', falling back: %s",
                settings.last_device,
                e,
            )

    fallback = available[0]
    if settings.last_device:
        log.info("last device unavailable, opening: %s", fallback)
    else:
        log.info("no last device in settings, opening: %s", fallback)
    try:
        return midi_output.open_output(fallback)
    except Exception as e:
        log.error("failed to open fallback device '%s': %s", fallback, e)
        return None


def main() -> int:
    _configure_logging()
    log = logging.getLogger(__name__)
    log.info("starting LinkBridge")

    settings = Settings.load()
    initial_port = _resolve_initial_device(settings)

    state = ClockState(lock=threading.Lock())
    state.start_stop_enabled = settings.start_stop_enabled
    state.midi_out = initial_port

    clock_engine = ClockEngine(state)
    link_monitor = LinkMonitor(state, initial_bpm=state.bpm)

    clock_engine.start()
    link_monitor.start()

    app = MenuBarApp(
        state=state,
        settings=settings,
        clock_engine=clock_engine,
        link_monitor=link_monitor,
    )
    try:
        app.run()
    finally:
        # Normal exit goes through MenuBarApp._on_quit_clicked which already
        # called these. Both stop() methods are idempotent so calling them
        # again on a clean shutdown is safe; the try/except guards an
        # unexpected exit from app.run().
        try:
            link_monitor.stop()
        except Exception as e:
            log.warning("teardown: link monitor stop failed: %s", e)
        try:
            clock_engine.stop()
        except Exception as e:
            log.warning("teardown: clock engine stop failed: %s", e)
        log.info("LinkBridge exited")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
