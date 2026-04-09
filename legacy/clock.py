#!/usr/bin/env python3

import ctypes
import time
import signal
import sys
import os
import asyncio
import threading
from aalink import Link

# Constants
BPM = 120
PPQN = 24  # Pulses Per Quarter Note

# ALSA MIDI Event Types (from alsa/asoundlib.h)
class MidiEventType:
    NOTEON = 6
    NOTEOFF = 7
    CONTROLLER = 10
    PGMCHANGE = 11
    PITCHBEND = 13
    CHANPRESS = 14
    KEYPRESS = 27

# Global state
running = True
midi_lib = None
tick_interval = None

# use float BPM with 0.1 precision
current_bpm = float(BPM)

# Define callback function type: void callback(int event_type, int channel, int param1, int param2, int param3)
MIDI_EVENT_CALLBACK = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int)

def midi_event_callback(event_type, channel, param1, param2, param3):
    """Callback function that receives MIDI events from C library and logs them."""
    # Channels are 0-indexed in C, but we display 1-indexed for users
    display_channel = channel + 1
    
    if event_type == MidiEventType.NOTEON:
        print(f"[Python] [MIDI IN] NOTE ON  - Channel: {display_channel}, Note: {param1}, Velocity: {param2}")
    elif event_type == MidiEventType.NOTEOFF:
        print(f"[Python] [MIDI IN] NOTE OFF - Channel: {display_channel}, Note: {param1}, Velocity: {param2}")
    elif event_type == MidiEventType.CONTROLLER:
        print(f"[Python] [MIDI IN] CC       - Channel: {display_channel}, Controller: {param1}, Value: {param2}")
    elif event_type == MidiEventType.PGMCHANGE:
        print(f"[Python] [MIDI IN] PROG CHG - Channel: {display_channel}, Program: {param1}")
    elif event_type == MidiEventType.PITCHBEND:
        print(f"[Python] [MIDI IN] PITCH BND - Channel: {display_channel}, Value: {param1} (range -8192 to 8191)")
    elif event_type == MidiEventType.CHANPRESS:
        print(f"[Python] [MIDI IN] AFTERTOUCH - Channel: {display_channel}, Value: {param1}")
    elif event_type == MidiEventType.KEYPRESS:
        print(f"[Python] [MIDI IN] POLY AFTERTOUCH - Channel: {display_channel}, Note: {param1}, Value: {param2}")

def change_tempo(new_bpm):
    """Change the tempo of the MIDI clock (applies to the C library).

    This function updates the C library tempo (if available) and recalculates
    the Python tick interval to keep timing in sync.
    """
    global midi_lib, current_bpm, tick_interval
    # new_bpm can be fractional (float). We send tempo to C in tenths (int)
    bpm10 = int(round(float(new_bpm) * 10.0))
    if midi_lib is None:
        # library not ready yet — just update local tempo so main loop picks it up
        current_bpm = float(new_bpm)
        tick_interval = calculate_tick_interval(current_bpm)
        print(f"[Python] Tempo updated locally -> {current_bpm:.1f} BPM (C lib not ready)")
        return

    if midi_lib.midi_set_tempo(bpm10) < 0:
        print(f"[Python] Warning: Failed to set tempo to {float(new_bpm):.1f} BPM in C library")
    else:
        current_bpm = float(new_bpm)
        tick_interval = calculate_tick_interval(current_bpm)
        print(f"[Python] Tempo changed -> {current_bpm:.1f} BPM")


def signal_handler(sig, frame):
    """Handle SIGINT (Ctrl+C) for clean shutdown"""
    global running
    print("\n[Python] Received SIGINT, shutting down...")
    running = False

def calculate_tick_interval(bpm):
    """Calculate the interval between MIDI clock ticks in seconds for given BPM"""
    ticks_per_second = (bpm / 60.0) * PPQN
    return 1.0 / ticks_per_second

def main():
    global running, midi_lib, tick_interval, current_bpm
    
    # Setup signal handler
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Load the C library
    lib_path = os.path.join(os.path.dirname(__file__), 'liblinkbridge.so')
    
    if not os.path.exists(lib_path):
        print(f"[Python] Error: Library not found at {lib_path}")
        print("[Python] Please compile the library first:")
        print("[Python]   gcc -shared -fPIC -o liblinkbridge.so midi_clock_lib.c -lasound")
        return 1
    
    try:
        midi_lib = ctypes.CDLL(lib_path)
    except OSError as e:
        print(f"[Python] Error loading library: {e}")
        return 1
    
    # Define function prototypes
    midi_lib.midi_init.restype = ctypes.c_int
    midi_lib.midi_send_start.restype = ctypes.c_int
    midi_lib.midi_send_clock.restype = ctypes.c_int
    midi_lib.midi_send_stop.restype = ctypes.c_int
    midi_lib.midi_get_tick_count.restype = ctypes.c_uint
    midi_lib.midi_get_client_id.restype = ctypes.c_int
    midi_lib.midi_get_port_id.restype = ctypes.c_int
    midi_lib.midi_get_queue_id.restype = ctypes.c_int
    midi_lib.midi_read_events.restype = ctypes.c_int
    midi_lib.midi_cleanup.restype = None
    # Expose tempo setter from C library
    midi_lib.midi_set_tempo.restype = ctypes.c_int
    midi_lib.midi_set_tempo.argtypes = [ctypes.c_int]
    
    # Setup event callback
    midi_lib.midi_register_event_callback.restype = None
    midi_lib.midi_register_event_callback.argtypes = [MIDI_EVENT_CALLBACK]
    
    # Create a persistent reference to the callback to prevent garbage collection
    callback_func = MIDI_EVENT_CALLBACK(midi_event_callback)
    
    print("[Python] Python MIDI Clock Generator")
    print("[Python] ============================")
    print(f"[Python] BPM: {BPM}, PPQN: {PPQN}")
    print()
    
    # Initialize MIDI
    print("[Python] Initializing ALSA MIDI...")
    if midi_lib.midi_init() < 0:
        print("[Python] Error: Failed to initialize MIDI")
        return 1
    
    # Register the event callback
    midi_lib.midi_register_event_callback(callback_func)

    # Set tempo in the C queue to match Python BPM (send tenths as int)
    if midi_lib.midi_set_tempo(int(round(current_bpm * 10.0))) < 0:
        print(f"[Python] Warning: Failed to set tempo to {current_bpm:.1f} BPM in C library")
    # initialize tick interval from current_bpm
    tick_interval = calculate_tick_interval(current_bpm)
    
    client_id = midi_lib.midi_get_client_id()
    port_id = midi_lib.midi_get_port_id()
    queue_id = midi_lib.midi_get_queue_id()
    
    print(f"[Python] ALSA Client ID: {client_id}")
    print(f"[Python] ALSA Port ID: {port_id}")
    print(f"[Python] ALSA Queue ID: {queue_id}")
    print(f"[Python] Connect with: aconnect {client_id}:{port_id} <destination>")
    print()
    print("[Python] Press Ctrl+C to stop")
    print()
    
    # Send MIDI Start
    if midi_lib.midi_send_start() < 0:
        print("[Python] Error: Failed to send MIDI START")
        midi_lib.midi_cleanup()
        return 1

    # Start Link monitor in a background thread to receive tempo updates
    def start_link_monitor():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def link_coroutine():
            link = Link(current_bpm, asyncio.get_running_loop())
            link.enabled = True
            link.start_stop_sync_enabled = True
            link.quantum = 4
            last_tempo = float(current_bpm)
            while running:
                try:
                    await link.sync(1)
                except Exception:
                    # if sync fails, wait a bit and continue
                    await asyncio.sleep(0.1)
                    continue

                # Always check tempo (Link can advertise tempo even when not playing)
                tempo = link.tempo
                if tempo is not None:
                    # update only on meaningful change to avoid noisy updates
                    if abs(float(tempo) - last_tempo) >= 0.01:
                        change_tempo(float(tempo))
                        last_tempo = float(tempo)

                # small sleep to yield and avoid busy-looping
                await asyncio.sleep(0.01)

        loop.run_until_complete(link_coroutine())

    monitor_thread = threading.Thread(target=start_link_monitor, daemon=True)
    monitor_thread.start()

    print(f"[Python] Tick interval: {tick_interval*1000:.3f} ms ({1/tick_interval:.1f} ticks/sec)")
    print()
    
    # Get start time for accurate timing
    next_tick_time = time.monotonic()
    tick_count = 0
    beat_count = 0
    
    # Main loop - send MIDI clock ticks
    try:
        while running:
            # Send MIDI Clock
            if midi_lib.midi_send_clock() < 0:
                print("[Python] Error: Failed to send MIDI CLOCK")
                break
            
            tick_count += 1
            
            # Print status every quarter note (24 ticks = 1 beat)
            if tick_count % PPQN == 0:
                beat_count += 1
                queue_tick = midi_lib.midi_get_tick_count()
                print(f"[Python] Beat {beat_count:4d} | MIDI Tick {tick_count:6d} | Queue Tick {queue_tick:6d}")
            
            # Check for new MIDI ports available
            numberOfHandledEvents = midi_lib.midi_read_events()

            # Sleep until next tick using absolute time to prevent drift
            next_tick_time += tick_interval
            sleep_time = next_tick_time - time.monotonic()
            
            if sleep_time > 0:
                time.sleep(sleep_time)
            else:
                # We're running behind - don't sleep, just continue
                # Reset next_tick_time to current time to resync
                if sleep_time < -tick_interval:
                    next_tick_time = time.monotonic()
    
    except Exception as e:
        print(f"[Python] Error in main loop: {e}")
    
    # Cleanup
    print()
    print("[Python] Stopping MIDI clock...")
    
    # Send MIDI Stop
    midi_lib.midi_send_stop()
    
    # Small delay to let the stop message be delivered
    time.sleep(0.1)
    
    # Cleanup ALSA resources
    midi_lib.midi_cleanup()
    
    print(f"[Python] Total ticks sent: {tick_count}")
    print(f"[Python] Total beats: {beat_count}")
    print("[Python] Shutdown complete")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())