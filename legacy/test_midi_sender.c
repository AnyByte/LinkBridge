#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <string.h>
#include <alsa/asoundlib.h>
#include <signal.h>
#include <termios.h>
#include <errno.h>

static int running = 1;
static snd_seq_t *seq_handle = NULL;
static int port_id = -1;
static struct termios original_tios;
static int terminal_set = 0;

void signal_handler(int sig) {
    running = 0;
    // Restore terminal immediately on signal
    if (terminal_set) {
        tcsetattr(STDIN_FILENO, TCSADRAIN, &original_tios);
        terminal_set = 0;
    }
    printf("\n\nShutting down gracefully...\n");
}

// Send a MIDI CC (Control Change) message
int send_midi_cc(int channel, int cc_number, int value) {
    int err;
    snd_seq_event_t ev;
    int my_client_id;
    
    my_client_id = snd_seq_client_id(seq_handle);
    
    // Clear event structure
    snd_seq_ev_clear(&ev);
    
    // Set event type to Controller (CC)
    snd_seq_ev_set_controller(&ev, channel - 1, cc_number, value);
    
    // Set the source to be this client and this port
    snd_seq_ev_set_source(&ev, port_id);
    
    // Set subscription mode - deliver to all subscribers
    snd_seq_ev_set_subs(&ev);
    
    // Set the event to be sent directly
    snd_seq_ev_set_direct(&ev);
    
    // Send the event
    err = snd_seq_event_output(seq_handle, &ev);
    if (err < 0) {
        fprintf(stderr, "Error sending MIDI event: %s\n", snd_strerror(err));
        return -1;
    }
    
    // Flush output to ensure event is sent
    snd_seq_drain_output(seq_handle);
    
    return 0;
}

// Initialize ALSA sequencer and create virtual MIDI port
int midi_init(void) {
    int err;
    
    // Open ALSA sequencer in DUPLEX mode for proper event routing
    err = snd_seq_open(&seq_handle, "default", SND_SEQ_OPEN_DUPLEX, 0);
    if (err < 0) {
        fprintf(stderr, "Error opening ALSA sequencer: %s\n", snd_strerror(err));
        return -1;
    }
    
    // Set client name
    snd_seq_set_client_name(seq_handle, "MIDI CC Sender");
    
    // Create output port
    port_id = snd_seq_create_simple_port(seq_handle, "MIDI Out",
                                          SND_SEQ_PORT_CAP_READ | SND_SEQ_PORT_CAP_SUBS_READ,
                                          SND_SEQ_PORT_TYPE_MIDI_GENERIC | SND_SEQ_PORT_TYPE_APPLICATION);
    if (port_id < 0) {
        fprintf(stderr, "Error creating port: %s\n", snd_strerror(port_id));
        snd_seq_close(seq_handle);
        seq_handle = NULL;
        return -1;
    }
    
    printf("MIDI CC Sender initialized\n");
    printf("Client ID: %d, Port ID: %d\n", snd_seq_client_id(seq_handle), port_id);
    printf("Connect this port to a MIDI destination using aconnect:\n");
    printf("  aconnect %d:%d <destination_client>:<destination_port>\n\n", 
           snd_seq_client_id(seq_handle), port_id);
    
    return 0;
}

// Cleanup ALSA resources
void midi_cleanup(void) {
    if (seq_handle != NULL) {
        snd_seq_close(seq_handle);
        seq_handle = NULL;
    }
}

// Set terminal to raw mode for immediate character input
void set_terminal_raw(struct termios *old_tios) {
    struct termios tios;
    
    tcgetattr(STDIN_FILENO, old_tios);
    tios = *old_tios;
    
    // Disable canonical mode and echo
    tios.c_lflag &= ~(ICANON | ECHO);
    tios.c_cc[VMIN] = 1;
    tios.c_cc[VTIME] = 0;
    
    tcsetattr(STDIN_FILENO, TCSADRAIN, &tios);
}

// Restore terminal to original mode
void restore_terminal(struct termios *tios) {
    tcsetattr(STDIN_FILENO, TCSADRAIN, tios);
}

int main(int argc, char *argv[]) {
    int err;
    unsigned char c;
    struct sigaction sa;
    
    // Setup signal handler with sigaction for more reliable handling
    memset(&sa, 0, sizeof(sa));
    sa.sa_handler = signal_handler;
    sigemptyset(&sa.sa_mask);
    sa.sa_flags = 0;
    sigaction(SIGINT, &sa, NULL);
    sigaction(SIGTERM, &sa, NULL);
    
    // Initialize MIDI
    if (midi_init() < 0) {
        return 1;
    }
    
    // Set terminal to raw mode for immediate character input
    set_terminal_raw(&original_tios);
    terminal_set = 1;
    
    printf("Press keys 1, 2, 3, or 4 to send MIDI CC messages\n");
    printf("Press Ctrl+C to exit\n\n");
    
    // Main input loop
    while (running) {
        err = read(STDIN_FILENO, &c, 1);
        
        // Handle signal interruption
        if (err < 0) {
            if (errno == EINTR && running) {
                // Signal interrupted the read, continue
                continue;
            }
            // Either an error or we were interrupted and should exit
            break;
        }
        
        if (err == 0) {
            continue;
        }
        
        // Determine which CC message to send based on input
        switch (c) {
            case '1':
                printf("Sending: MIDI CC 1, value 127 on channel 1\n");
                send_midi_cc(1, 1, 127);
                break;
            case '2':
                printf("Sending: MIDI CC 2, value 127 on channel 1\n");
                send_midi_cc(1, 2, 127);
                break;
            case '3':
                printf("Sending: MIDI CC 3, value 127 on channel 1\n");
                send_midi_cc(1, 3, 127);
                break;
            case '4':
                printf("Sending: MIDI CC 4, value 127 on channel 1\n");
                send_midi_cc(1, 4, 127);
                break;
            case 'q':
            case 'Q':
                printf("\nExiting...\n");
                running = 0;
                break;
            default:
                // Ignore other characters
                break;
        }
    }
    
    // Restore terminal mode if it was set
    if (terminal_set) {
        restore_terminal(&original_tios);
        terminal_set = 0;
    }
    
    // Cleanup
    midi_cleanup();
    printf("Cleanup complete. Goodbye!\n");
    
    return 0;
}
