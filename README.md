# LinkBridge

A tiny macOS menu bar app that forwards Ableton Link tempo to a hardware MIDI
output. Drop it next to a Link-enabled DJ app or DAW and any MIDI gear that
syncs to incoming MIDI clock will follow the tempo in real time.

```
  ┌──────────────┐    Link    ┌──────────────┐    MIDI clock    ┌──────────────┐
  │  djay Pro /  │ ─────────▶ │  LinkBridge  │ ───────────────▶ │  Hardware    │
  │  Live / etc. │            │  (menu bar)  │   (CoreMIDI)     │  MIDI device │
  └──────────────┘            └──────────────┘                  └──────────────┘
```

## Requirements

- macOS 15 (Sequoia) or later, Apple Silicon (tested on M2 Pro)
- Python 3.11 or 3.12 (only needed for running from source / building the .app)
- A USB-connected MIDI device with external clock support
- An Ableton Link source on the same machine or LAN

## Quick start (from source)

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m linkbridge
```

A `♪ <bpm>` icon appears in the macOS menu bar within a few seconds. Click
it, choose your MIDI output device from the **Output Device** submenu, and
the clock starts streaming as soon as a Link peer reports a tempo.

## Build a standalone `.app`

```bash
source venv/bin/activate
pip install -r requirements-dev.txt
./scripts/build_app.sh
```

The bundle is produced at `dist/LinkBridge.app`. To package it as a
distributable disk image:

```bash
./scripts/build_dmg.sh 2.0.0
```

This produces `dist/LinkBridge-v2.0.0.dmg` containing `LinkBridge.app`
plus a symlink to `/Applications` for drag-to-install. Releases on
GitHub Releases ship the `.dmg` exclusively.

**Installation flow:**

- Download `LinkBridge-v<version>.dmg` from the
  [latest release](https://github.com/AnyByte/LinkBridge/releases/latest)
- Double-click the `.dmg` to mount it
- Drag `LinkBridge.app` onto the `Applications` shortcut in the disk
  image window
- Eject the disk image
- Launch from `/Applications`

**On first launch:**

- The bundle is **unsigned** (no Apple Developer ID). macOS Gatekeeper
  may block it the first time — right-click the `.app` in Finder, choose
  **Open**, confirm the warning, then launch normally afterwards.
- macOS asks for **local network permission** ("Allow LinkBridge to find
  devices on local networks?"). Click **Allow**, otherwise Ableton Link
  cannot discover any peers and the tempo stays at the default 120 BPM
  forever. The bundle includes a description string explaining what the
  permission is used for.

## Menu reference

```
♪ 125.0
────────────
Output Device  ▸  ● Circuit Tracks MIDI
                  ○ DDJ-FLX4
                  ────
                  ↻ Refresh devices
Enable Start/Stop events  ☐
────────────
Quit
```

| Item | Behavior |
|---|---|
| `♪ <bpm>` | Live tempo from the active Link peer. Shows `♪ --` when no MIDI device is selected, `♪ ERR` if the clock thread crashed. |
| **Output Device** | All available CoreMIDI outputs. Pick one to route clock to it. The choice is remembered for next launch. `↻ Refresh devices` rebuilds the list — useful after plugging in a new USB device. |
| **Enable Start/Stop events** | When ON, sends MIDI `START` on Link play and MIDI `STOP` on Link stop. Default OFF. The clock tick stream itself is **always** running once a device is selected, regardless of this toggle. |
| **Quit** | Sends a final MIDI STOP if needed, closes the port, exits cleanly. |

## Compatibility — which DJ software works?

LinkBridge passes through whatever Ableton Link tempo it can see. The
catch is that **not every DJ app broadcasts its deck tempo to Link** — most
of them only listen.

### "Just works" — fully automatic

These apps act as Link tempo masters when a deck is playing, so LinkBridge
picks up the tempo automatically with zero manual steps:

- **djay Pro for Mac** (Algoriddim) — officially supports the DDJ-FLX4 and
  many other Pioneer / Numark / Reloop controllers; the playing deck
  becomes the Link master automatically.
- **Mixxx 2.5+** — open source, free, ships with a community DDJ-FLX4
  mapping and bidirectional Link support.
- **Ableton Live**, **Logic Pro** with Link, **GarageBand**, and any other
  Link-aware DAW — playing the timeline broadcasts tempo to Link.

### Works with a small manual step — Rekordbox

**Rekordbox 7.x has a hard one-way Link integration:** the LINK button on
each deck makes that deck *follow* Link, but Rekordbox does **not**
broadcast the playing deck's tempo back to Link. This is a Rekordbox
limitation, not a LinkBridge bug. See Pioneer's
[Ableton Link FAQ](https://rekordbox.com/en/support/faq/ableton-link/) and
this [community feature request](https://forums.pioneerdj.com/hc/en-us/community/posts/900002865663-Ableton-Link-in-Rekordbox-Suggestion-Follow-the-Master-Deck-BPM-option).

To use LinkBridge with Rekordbox, drive the Link tempo manually from
Rekordbox's Ableton Link sub-window:

1. Open Rekordbox and open its **Ableton Link** sub-window (the small
   window with the BPM display, `TAP`, `+`, `-` buttons).
2. Read the BPM of the track currently loaded on your master deck.
3. Type or click that BPM into the Link sub-window using the `+`/`-`
   buttons (or use `TAP` to find it by ear).
4. LinkBridge picks it up immediately and your hardware follows.
5. When you change tracks, repeat — Rekordbox does not auto-update Link.

> **Note about the tempo slider:** When a hardware controller like the
> DDJ-FLX4 is connected, Rekordbox disables the on-screen TEMPO slider for
> Link control entirely. The Link sub-window's `+`/`-` buttons (or MIDI-
> mapped equivalents) are the only way to drive Link tempo from a
> controller-attached Rekordbox session.

If the manual workflow is too tedious for your set, the
[`rkbx_link`](https://github.com/grufkork/rkbx_link) project reads
Rekordbox's process memory directly and pushes the master deck's tempo
into Link automatically. It requires re-signing Rekordbox to add the
`get-task-allow` entitlement and running with `sudo` — see its
`MACOS_SETUP.md` for details. LinkBridge does not currently bundle this
behaviour but composes cleanly with `rkbx_link` if you run them
side-by-side.

## Using with Novation Circuit Tracks

The Circuit Tracks needs one Setup-view setting before it accepts external
clock — this is a one-time change that persists across reboots.

1. On the Circuit Tracks, hold **Shift** and press **Save** to enter
   Setup view.
2. On the bottom row of pads find the four "MIDI data control" Rx/Tx
   pads. The rightmost pair is **MIDI Clock Rx/Tx**. Make sure **Clock
   Rx** is lit (factory default is OFF).
3. Press **Play** on the Circuit Tracks to exit Setup view.

After that:

- Launch LinkBridge and pick **Circuit Tracks MIDI** from the Output
  Device submenu.
- If the Circuit Tracks is **stopped** when LinkBridge starts streaming
  clock, it instantly enters external sync mode — the Tempo/Swing view
  shows `SYN` in red. Press Play and the pattern follows the incoming
  tempo.
- If the Circuit Tracks was **already playing an internal pattern** when
  LinkBridge connected, it ignores the incoming clock and keeps playing
  at its internal tempo. **Recovery is one button press:** tap **Stop**
  on the Circuit Tracks; `SYN` appears immediately because the clock
  stream was already flowing. Press Play again and you're locked.
- When LinkBridge quits, the clock stream stops, `SYN` disappears, and
  the Circuit Tracks reverts to internal clock — any pattern that was
  playing via SYN halts.

This behaviour is the Circuit Tracks's, not LinkBridge's. Most other
class-compliant USB MIDI gear follows incoming clock without any
external-sync arming step.

## Files and logs

| Path | Purpose |
|---|---|
| `~/Library/Application Support/LinkBridge/settings.json` | Last selected device and Start/Stop toggle state |
| `~/Library/Logs/LinkBridge/linkbridge.log` | Rotating log file (1 MB × 3) |

Set `LINKBRIDGE_DEBUG=1` in the environment for verbose logging:

```bash
LINKBRIDGE_DEBUG=1 python -m linkbridge
```

## Architecture

A single Python process with three threads sharing a lock-guarded
`ClockState` dataclass:

| Thread | Module | Job |
|---|---|---|
| Main | `linkbridge/app.py` | rumps menu bar UI, 500 ms label refresh |
| Clock | `linkbridge/clock_engine.py` | 24 ppqn MIDI clock generator with drift compensation |
| Link | `linkbridge/link_monitor.py` | aalink callback loop pushing tempo + transport into ClockState |

The Settings store and the MidiOutput helpers (`linkbridge/settings.py`,
`linkbridge/midi_output.py`) are stateless utilities used by the threads
above.

## Tests

```bash
source venv/bin/activate
pytest
```

22 unit tests cover Settings, MidiOutput, and ClockEngine using fake
clocks / fake MIDI sinks — no hardware or Link peer required. The Link
monitor and the menu bar app are validated by manual smoke tests against
real hardware (the smoke procedure is documented in the project plan).

## Releasing a new version

Releases are cut by a single click in the **GitHub Actions** tab — no local
commands or git tagging required.

1. Go to https://github.com/AnyByte/LinkBridge/actions/workflows/release.yml
2. Click **Run workflow**
3. Type the new version (e.g. `2.1.0`, no `v` prefix)
4. Click **Run workflow**

The CI will then:

- Bump the version strings in `linkbridge/__init__.py` and `setup.py`
- Commit and tag the bump on `main` (`v2.1.0`)
- Run the test suite
- Build `LinkBridge.app` and zip it via `ditto`
- Create a **draft** GitHub Release with auto-generated notes (built from
  the conventional-commit history since the previous tag) and the
  `LinkBridge-v2.1.0.zip` attached

Find the draft release on the
[Releases page](https://github.com/AnyByte/LinkBridge/releases), edit the
notes if you want, then click **Publish release**.

You can also trigger the workflow from a terminal:

```bash
gh workflow run release.yml -f version=2.1.0
gh run watch  # follow the build
```

The release workflow uses [`bump-my-version`](https://github.com/callowayproject/bump-my-version)
under the hood (file list in `pyproject.toml`) and prepends each new
release section to [`CHANGELOG.md`](CHANGELOG.md) via
`scripts/update_changelog.py`. The changelog entries are auto-generated
from the pull requests merged since the previous tag using GitHub's
release-notes API.

## Regenerating the app icon

The icon source is `assets/icon.png` (1024×1024). To rebuild the
`assets/LinkBridge.icns` file from a fresh source PNG:

```bash
.venv-probe/bin/pip install Pillow  # or any venv with Pillow available
python3 scripts/build_icon.py
```

The script flood-fills the white background to transparent, crops to the
non-transparent bbox, generates all 10 macOS iconset sizes, and runs
`iconutil` to produce the final `.icns`.

## Legacy Linux implementation

The original ALSA / C Linux implementation lives in `legacy/` for
reference and is not maintained. If you want to run that on Linux, the
build commands are at the top of `legacy/midi_clock_lib.c` — but the
macOS port in this branch is the only thing actively developed.

## License

See `LICENSE`.
