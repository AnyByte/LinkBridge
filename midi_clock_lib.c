#include <stdio.h>
#include <stdlib.h>
#include <alsa/asoundlib.h>

#define BPM 120
#define PPQN 24
#define QUEUE_TEMPO_PPQ 96

// Event callback type - called when MIDI events are received
// event_type: one of the SND_SEQ_EVENT_* constants
// channel: MIDI channel (0-15)
// param1, param2, param3: event-specific parameters
typedef void (*midi_event_callback_t)(int event_type, int channel, int param1, int param2, int param3);

// Global handles
static snd_seq_t *seq_handle = NULL;
static int port_id = -1;
static int queue_id = -1;
static snd_seq_tick_time_t current_queue_tick = 0;
static char virtualMidiPortName[] = "LinkBridge MIDI Clock";
/* highest tick we've scheduled so far (used to place tempo changes after all
    previously queued events) */
static snd_seq_tick_time_t max_scheduled_tick = 0;

// Global callback function pointer
static midi_event_callback_t event_callback = NULL;

// Forward declarations
static int has_write_capability(snd_seq_t *seq, int client, int port);
static int has_read_capability(snd_seq_t *seq, int client, int port);

// Register a callback function for MIDI events
// Call this from Python to set up the event handler
void midi_register_event_callback(midi_event_callback_t callback) {
    event_callback = callback;
    if (callback != NULL) {
        printf("[C] MIDI event callback registered\n");
    }
}

// Connect to all existing MIDI ports on startup (except ports 0 and 14)
static void midi_connect_all_ports(void) {
    if (seq_handle == NULL)
        return;

    snd_seq_client_info_t *cinfo;
    snd_seq_port_info_t *pinfo;
    int client;
    
    snd_seq_client_info_alloca(&cinfo);
    snd_seq_port_info_alloca(&pinfo);
    
    snd_seq_client_info_set_client(cinfo, -1);
        
    // Iterate through all clients
    while (snd_seq_query_next_client(seq_handle, cinfo) >= 0) {
        client = snd_seq_client_info_get_client(cinfo);
        
        // Ignore ourselves
        if (client == snd_seq_client_id(seq_handle))
            continue;

        // Ignore System and Midi Throught devices
        if (client == 0 || client == 14)
            continue;
        
        snd_seq_port_info_set_client(pinfo, client);
        snd_seq_port_info_set_port(pinfo, -1);
        
        // Iterate through all ports of this client
        while (snd_seq_query_next_port(seq_handle, pinfo) >= 0) {
            int port = snd_seq_port_info_get_port(pinfo);
            
            
            if (has_write_capability(seq_handle, client, port)) {
                printf("[C] Connecting %s -> %d:%d\n", virtualMidiPortName, client, port);
                snd_seq_connect_to(seq_handle, port_id, client, port);
            }
            
            if (has_read_capability(seq_handle, client, port)) {
                printf("[C] Connecting %d:%d -> %s\n", client, port, virtualMidiPortName);
                snd_seq_connect_from(seq_handle, port_id, client, port);
            }
        }
    }
}

// Initialize ALSA sequencer, create port and queue
// Returns 0 on success, -1 on error
int midi_init(void) {
    int err;
    snd_seq_queue_tempo_t *queue_tempo;
        printf("[C] Initializing MIDI subsystem...\n");
        // Open ALSA sequencer
    err = snd_seq_open(&seq_handle, "default", SND_SEQ_OPEN_DUPLEX, 0);
    if (err < 0) {
        fprintf(stderr, "[C] Error opening ALSA sequencer: %s\n", snd_strerror(err));
        return -1;
    }
    
    // Set non-blocking mode so snd_seq_event_input() doesn't hang
    snd_seq_nonblock(seq_handle, 1);

    // Set client name
    snd_seq_set_client_name(seq_handle, virtualMidiPortName);
    
    // Create output port
    port_id = snd_seq_create_simple_port(seq_handle, "MIDI Clock Out",
                                          SND_SEQ_PORT_CAP_READ | SND_SEQ_PORT_CAP_SUBS_READ | SND_SEQ_PORT_CAP_WRITE | SND_SEQ_PORT_CAP_SUBS_WRITE,
                                          SND_SEQ_PORT_TYPE_MIDI_GENERIC | SND_SEQ_PORT_TYPE_APPLICATION);
    if (port_id < 0) {
        fprintf(stderr, "[C] Error creating port: %s\n", snd_strerror(port_id));
        snd_seq_close(seq_handle);
        seq_handle = NULL;
        return -1;
    }

    /* Subscribe to system announce */
    if ((err = snd_seq_connect_from(
            seq_handle,
            port_id,
            SND_SEQ_CLIENT_SYSTEM,
            SND_SEQ_PORT_SYSTEM_ANNOUNCE)) < 0) {
        fprintf(stderr, "[C] Cannot subscribe to system announce: %s\n",
                snd_strerror(err));
        exit(1);
    }

    printf("[C] Listening for PORT_START events...\n");
    
    // Create queue
    queue_id = snd_seq_alloc_queue(seq_handle);
    if (queue_id < 0) {
        fprintf(stderr, "[C] Error creating queue: %s\n", snd_strerror(queue_id));
        snd_seq_close(seq_handle);
        seq_handle = NULL;
        return -1;
    }
    
    // Set initial queue tempo using BPM macro (support tenths precision)
    snd_seq_queue_tempo_alloca(&queue_tempo);
    unsigned int init_us_per_beat = 600000000U / (BPM * 10); // BPM macro is integer
    snd_seq_queue_tempo_set_tempo(queue_tempo, init_us_per_beat);
    snd_seq_queue_tempo_set_ppq(queue_tempo, QUEUE_TEMPO_PPQ);
    err = snd_seq_set_queue_tempo(seq_handle, queue_id, queue_tempo);
    if (err < 0) {
        fprintf(stderr, "[C] Error setting queue tempo: %s\n", snd_strerror(err));
        snd_seq_free_queue(seq_handle, queue_id);
        snd_seq_close(seq_handle);
        seq_handle = NULL;
        return -1;
    }
    
    printf("[C] MIDI initialized: Client %d, Port %d, Queue %d\n", 
           snd_seq_client_id(seq_handle), port_id, queue_id);
    
    current_queue_tick = 0;
    
    // Connect to all existing MIDI ports on startup
    midi_connect_all_ports();
    
    return 0;
}

// Update the queue tempo using BPM value
// Returns 0 on success, -1 on error
// Update the queue tempo using BPM value expressed in tenths (e.g. 1200 = 120.0 BPM)
// Returns 0 on success, -1 on error
int midi_set_tempo(int bpm10) {
    if (seq_handle == NULL) {
        fprintf(stderr, "[C] Error: MIDI not initialized\n");
        return -1;
    }
    if (bpm10 <= 0) {
        fprintf(stderr, "[C] Error: invalid BPM (tenths) %d\n", bpm10);
        return -1;
    }

    /* bpm10 is BPM * 10. To compute microseconds per beat:
     * us_per_beat = 60000000 / BPM = 60000000 / (bpm10 / 10) = 600000000 / bpm10
     */
    unsigned int us_per_beat = 600000000U / (unsigned int)bpm10;

    /*
     * Instead of applying the tempo immediately (which would change the
     * tick->time mapping for all remaining queued tick events), enqueue a
     * queue-tempo event scheduled at a future tick. Events already enqueued
     * at earlier ticks will keep their original timing.
     */
    snd_seq_event_t ev;
    snd_seq_ev_clear(&ev);
    snd_seq_ev_set_source(&ev, port_id);
    snd_seq_ev_set_subs(&ev);


     /* attach the tempo (microseconds per beat) to the event using ALSA
         helper macro. The macro expects the tempo value (not a pointer). */
     snd_seq_ev_set_queue_tempo(&ev, queue_id, us_per_beat);

     /* schedule the tempo change at the next tick after the highest tick
         we've already scheduled. This ensures earlier enqueued events keep
         their original timing. */
     snd_seq_tick_time_t target_tick = max_scheduled_tick + 1;
    snd_seq_ev_schedule_tick(&ev, queue_id, 0, target_tick);

    int err = snd_seq_event_output(seq_handle, &ev);
    if (err < 0) {
        fprintf(stderr, "[C] Error enqueuing tempo event: %s\n", snd_strerror(err));
        return -1;
    }
    snd_seq_drain_output(seq_handle);

        printf("[C] MIDI tempo (queued) set to %.1f BPM ( %u us/beat ) at tick %lu\n",
            bpm10 / 10.0, us_per_beat, (unsigned long)target_tick);
    return 0;
}

// Send MIDI Start message
// Returns 0 on success, -1 on error
int midi_send_start(void) {
    if (seq_handle == NULL) {
        fprintf(stderr, "[C] Error: MIDI not initialized\n");
        return -1;
    }
    
    snd_seq_event_t ev;
    snd_seq_ev_clear(&ev);
    snd_seq_ev_set_source(&ev, port_id);
    snd_seq_ev_set_subs(&ev);
    ev.type = SND_SEQ_EVENT_START;
    
    snd_seq_ev_schedule_tick(&ev, queue_id, 0, 0);
    snd_seq_event_output(seq_handle, &ev);
    snd_seq_drain_output(seq_handle);
    
    // Start the queue
    snd_seq_start_queue(seq_handle, queue_id, NULL);
    snd_seq_drain_output(seq_handle);
    
    printf("[C] MIDI START sent, queue started\n");
    
    if (0 > max_scheduled_tick) max_scheduled_tick = 0;

    return 0;
}

// Send MIDI Clock message
// Returns 0 on success, -1 on error
int midi_send_clock(void) {
    if (seq_handle == NULL) {
        fprintf(stderr, "[C] Error: MIDI not initialized\n");
        return -1;
    }
    
    snd_seq_event_t ev;
    snd_seq_ev_clear(&ev);
    snd_seq_ev_set_source(&ev, port_id);
    snd_seq_ev_set_subs(&ev);
    ev.type = SND_SEQ_EVENT_CLOCK;
    
    snd_seq_ev_schedule_tick(&ev, queue_id, 0, current_queue_tick);
    snd_seq_event_output(seq_handle, &ev);
    snd_seq_drain_output(seq_handle);
    
    // Advance queue tick by ratio (96 PPQ / 24 PPQN = 4 ticks per MIDI clock)
    current_queue_tick += (QUEUE_TEMPO_PPQ / PPQN);
    if (current_queue_tick > max_scheduled_tick) max_scheduled_tick = current_queue_tick;
    
    return 0;
}

// Send MIDI Stop message
// Returns 0 on success, -1 on error
int midi_send_stop(void) {
    if (seq_handle == NULL) {
        fprintf(stderr, "[C] Error: MIDI not initialized\n");
        return -1;
    }
    
    snd_seq_event_t ev;
    snd_seq_ev_clear(&ev);
    snd_seq_ev_set_source(&ev, port_id);
    snd_seq_ev_set_subs(&ev);
    ev.type = SND_SEQ_EVENT_STOP;
    
    snd_seq_ev_schedule_tick(&ev, queue_id, 0, current_queue_tick);
    snd_seq_event_output(seq_handle, &ev);
    snd_seq_drain_output(seq_handle);
    
    printf("[C] MIDI STOP sent\n");
    
    return 0;
}

// Get current tick count
unsigned int midi_get_tick_count(void) {
    return current_queue_tick;
}

// Cleanup and close ALSA sequencer
void midi_cleanup(void) {
    if (seq_handle != NULL) {
        if (queue_id >= 0) {
            snd_seq_stop_queue(seq_handle, queue_id, NULL);
            snd_seq_free_queue(seq_handle, queue_id);
        }
        snd_seq_close(seq_handle);
        seq_handle = NULL;
        port_id = -1;
        queue_id = -1;
        printf("[C] MIDI cleanup complete\n");
    }
}

// Get client ID
int midi_get_client_id(void) {
    if (seq_handle == NULL) return -1;
    return snd_seq_client_id(seq_handle);
}

// Get port ID
int midi_get_port_id(void) {
    return port_id;
}

// Get queue ID
int midi_get_queue_id(void) {
    return queue_id;
}

// Check if the MIDI port is able to send MIDI messages (for us to send data to)
static int has_write_capability(snd_seq_t *seq, int client, int port)
{
    snd_seq_port_info_t *pinfo;
    snd_seq_port_info_alloca(&pinfo);

    if (snd_seq_get_any_port_info(seq, client, port, pinfo) < 0)
        return 0;

    unsigned int caps = snd_seq_port_info_get_capability(pinfo);

    return (caps & SND_SEQ_PORT_CAP_WRITE) &&
           (caps & SND_SEQ_PORT_CAP_SUBS_WRITE);
}

// Check if the MIDI port is able to receive MIDI messages
static int has_read_capability(snd_seq_t *seq, int client, int port)
{
    snd_seq_port_info_t *pinfo;
    snd_seq_port_info_alloca(&pinfo);

    if (snd_seq_get_any_port_info(seq, client, port, pinfo) < 0)
        return 0;

    unsigned int caps = snd_seq_port_info_get_capability(pinfo);

    return (caps & SND_SEQ_PORT_CAP_READ) &&
           (caps & SND_SEQ_PORT_CAP_SUBS_READ);
}

// Poll ALSA sequencer events for PORT_START when a new MIDI device is connected
int midi_read_events(void) {
    if (seq_handle == NULL) {
        fprintf(stderr, "[C] Error: MIDI not initialized\n");
        return -1;
    }

    snd_seq_event_t *event;
    int count = 0;
    
    // Non-blocking event read loop
    while (snd_seq_event_input(seq_handle, &event) > 0) {
        if (event->type == SND_SEQ_EVENT_PORT_START) {
            // Handle new port detection here for auto-connect

            int client = event->data.addr.client;
            int port   = event->data.addr.port;

            /* Ignore ourselves */
            if (client == snd_seq_client_id(seq_handle))
                continue;

            printf("[C] New port: %d:%d\n", client, port);

            if (has_write_capability(seq_handle, client, port)) {

                printf("[C] Connecting %s -> %d:%d\n", virtualMidiPortName, client, port);

                snd_seq_connect_to(
                    seq_handle,
                    port_id,
                    client,
                    port);
            }

            if (has_read_capability(seq_handle, client, port)) {

                printf("[C] Connecting %d:%d -> %s\n", client, port,virtualMidiPortName);

                snd_seq_connect_from(
                    seq_handle,
                    port_id,
                    client,
                    port);
            }
        }
        else if (event->type == SND_SEQ_EVENT_NOTEON) {
            if (event_callback != NULL) {
                event_callback(SND_SEQ_EVENT_NOTEON,
                              event->data.note.channel,
                              event->data.note.note,
                              event->data.note.velocity,
                              0);
            }
        }
        else if (event->type == SND_SEQ_EVENT_NOTEOFF) {
            if (event_callback != NULL) {
                event_callback(SND_SEQ_EVENT_NOTEOFF,
                              event->data.note.channel,
                              event->data.note.note,
                              event->data.note.velocity,
                              0);
            }
        }
        else if (event->type == SND_SEQ_EVENT_CONTROLLER) {
            if (event_callback != NULL) {
                event_callback(SND_SEQ_EVENT_CONTROLLER,
                              event->data.control.channel,
                              event->data.control.param,
                              event->data.control.value,
                              0);
            }
        }
        else if (event->type == SND_SEQ_EVENT_PGMCHANGE) {
            if (event_callback != NULL) {
                event_callback(SND_SEQ_EVENT_PGMCHANGE,
                              event->data.control.channel,
                              event->data.control.value,
                              0,
                              0);
            }
        }
        else if (event->type == SND_SEQ_EVENT_PITCHBEND) {
            if (event_callback != NULL) {
                event_callback(SND_SEQ_EVENT_PITCHBEND,
                              event->data.control.channel,
                              event->data.control.value,
                              0,
                              0);
            }
        }
        else if (event->type == SND_SEQ_EVENT_CHANPRESS) {
            if (event_callback != NULL) {
                event_callback(SND_SEQ_EVENT_CHANPRESS,
                              event->data.control.channel,
                              event->data.control.value,
                              0,
                              0);
            }
        }
        else if (event->type == SND_SEQ_EVENT_KEYPRESS) {
            if (event_callback != NULL) {
                event_callback(SND_SEQ_EVENT_KEYPRESS,
                              event->data.note.channel,
                              event->data.note.note,
                              event->data.note.velocity,
                              0);
            }
        }
        count++;
    }
    
    return count;
}