"""Menu bar app built on rumps. Runs on the main thread."""

from __future__ import annotations

import logging

import rumps

from linkbridge import midi_output
from linkbridge.clock_engine import ClockEngine, ClockState
from linkbridge.link_monitor import LinkMonitor
from linkbridge.settings import Settings

log = logging.getLogger(__name__)

MENU_DEVICE_HEADER = "Output Device"
MENU_TOGGLE_TITLE = "Enable Start/Stop events"
MENU_REFRESH_TITLE = "↻ Refresh devices"
MENU_NO_DEVICE = "(no MIDI output)"
LABEL_NO_DEVICE = "♪ --"
LABEL_CRASHED = "♪ ERR"


def _format_bpm(bpm: float) -> str:
    return f"♪ {bpm:.1f}"


class MenuBarApp(rumps.App):
    def __init__(
        self,
        state: ClockState,
        settings: Settings,
        clock_engine: ClockEngine,
        link_monitor: LinkMonitor,
    ) -> None:
        super().__init__("LinkBridge", title=_format_bpm(state.bpm), quit_button=None)
        self.state = state
        self.settings = settings
        self.clock_engine = clock_engine
        self.link_monitor = link_monitor

        self._device_menu = rumps.MenuItem(MENU_DEVICE_HEADER)
        self._toggle_item = rumps.MenuItem(
            MENU_TOGGLE_TITLE, callback=self._on_toggle_clicked
        )
        self._toggle_item.state = 1 if state.start_stop_enabled else 0
        self._quit_item = rumps.MenuItem("Quit", callback=self._on_quit_clicked)

        self.menu = [
            self._device_menu,
            self._toggle_item,
            None,  # separator
            self._quit_item,
        ]
        self._rebuild_device_menu()

        self._refresh_timer = rumps.Timer(self._on_timer_tick, 0.5)
        self._refresh_timer.start()

    # ----- menu building -----

    def _rebuild_device_menu(self) -> None:
        try:
            outputs = midi_output.list_outputs()
        except Exception as e:
            log.error("list_outputs failed: %s", e)
            outputs = []

        with self.state.lock:
            current_port = self.state.midi_out
        current_name = getattr(current_port, "name", None) if current_port else None

        self._device_menu.clear()
        if not outputs:
            self._device_menu.add(rumps.MenuItem(MENU_NO_DEVICE))
        else:
            for name in outputs:
                item = rumps.MenuItem(
                    name, callback=self._make_device_callback(name)
                )
                item.state = 1 if name == current_name else 0
                self._device_menu.add(item)
        self._device_menu.add(None)
        self._device_menu.add(
            rumps.MenuItem(MENU_REFRESH_TITLE, callback=self._on_refresh_clicked)
        )

    def _make_device_callback(self, name: str):
        def cb(_sender):
            self._on_device_selected(name)
        return cb

    # ----- callbacks -----

    def _on_device_selected(self, name: str) -> None:
        log.info("user picked device: %s", name)
        try:
            new_port = midi_output.open_output(name)
        except Exception as e:
            log.error("failed to open %s: %s", name, e)
            rumps.alert("LinkBridge", f"Could not open '{name}':\n{e}")
            return

        with self.state.lock:
            old_port = self.state.midi_out
            self.state.midi_out = new_port
        if old_port is not None:
            try:
                old_port.close()
            except Exception as e:
                log.warning("closing old port failed: %s", e)

        self.settings.last_device = name
        try:
            self.settings.save()
        except Exception as e:
            log.warning("settings save failed: %s", e)

        self._rebuild_device_menu()

    def _on_refresh_clicked(self, _sender) -> None:
        log.info("refresh requested")
        self._rebuild_device_menu()

    def _on_toggle_clicked(self, sender) -> None:
        new_value = not bool(sender.state)
        with self.state.lock:
            self.state.start_stop_enabled = new_value
        sender.state = 1 if new_value else 0
        self.settings.start_stop_enabled = new_value
        try:
            self.settings.save()
        except Exception as e:
            log.warning("settings save failed: %s", e)
        log.info("start/stop toggle -> %s", "ON" if new_value else "OFF")

    def _on_quit_clicked(self, _sender) -> None:
        log.info("quit clicked — shutting down")
        try:
            self.link_monitor.stop()
        except Exception as e:
            log.warning("link monitor stop failed: %s", e)
        try:
            self.clock_engine.stop()
        except Exception as e:
            log.warning("clock engine stop failed: %s", e)
        rumps.quit_application()

    def _on_timer_tick(self, _timer) -> None:
        with self.state.lock:
            bpm = self.state.bpm
            has_port = self.state.midi_out is not None
            crashed = self.state.clock_crashed
        if crashed:
            self.title = LABEL_CRASHED
        elif not has_port:
            self.title = LABEL_NO_DEVICE
        else:
            self.title = _format_bpm(bpm)
