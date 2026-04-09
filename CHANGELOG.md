# Changelog

All notable changes to LinkBridge are documented here, in reverse
chronological order. From v2.0.1 onwards, new entries are appended
automatically by the [`release.yml`](.github/workflows/release.yml)
workflow on each release — they list every pull request merged since
the previous version. The v2.0.0 entry below was hand-written because
it predates the automation.

The format roughly follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

<!-- changelog-insertion-point -->

## [v2.0.0](https://github.com/AnyByte/LinkBridge/releases/tag/v2.0.0) — 2026-04-09 — macOS port

Initial macOS port release. Replaces the original Linux/ALSA implementation
with a pure-Python macOS menu bar app. The Linux sources are archived under
`legacy/` and are no longer maintained.

### What's Changed

- Merge macOS port ([#1](https://github.com/AnyByte/LinkBridge/pull/1)) — full rewrite for macOS, packaged as `LinkBridge.app`

### Highlights

- Pure-Python menu bar app built on `rumps` (no native code of our own)
- Bidirectional MIDI via `mido` + `python-rtmidi` over CoreMIDI
- 24 ppqn clock generator with drift-compensated absolute-time scheduling
- Reactive Ableton Link integration via `aalink` callbacks (no polling)
- Settings persistence at `~/Library/Application Support/LinkBridge/settings.json`
- Distributed as a double-clickable `LinkBridge.app` bundle (custom icon, `LSUIElement`)
- 22 unit tests covering Settings, MidiOutput, and ClockEngine
- py2app build via `./scripts/build_app.sh`
- GitHub Actions CI: tests on every PR, releases via `workflow_dispatch`

### Compatibility

Works with any host that broadcasts Ableton Link tempo: djay Pro, Mixxx,
Ableton Live, Logic Pro, GarageBand. **Rekordbox 7.x** has a one-way Link
integration, so manual tempo entry in the Link sub-window is required —
see the [README](README.md) for the workflow.
