#!/usr/bin/env python3
"""
MIDI Sampler for Piano Player Project

This script listens for MIDI input and plays audio samples mapped to keys.
It uses pygame for both audio playback and MIDI input (via mido).

Key Features:
- Robust MIDI device handling with proper cleanup
- Signal handling to ensure device release on crash/exit
- Fallback to pygame.midi if mido fails
"""

import os
import sys
import time
import argparse
import signal

# Force unbuffered output for better debugging
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)

# Third-party libraries
try:
    import mido
except ImportError:
    print("Error: The 'mido' library is required. Please install it with 'pip install mido'.")
    sys.exit(1)

try:
    import pygame
    import pygame.midi
except ImportError:
    print("Error: The 'pygame' library is required. Please install it with 'pip install pygame'.")
    sys.exit(1)


# --- Global State ---
current_channel = None 
midi_port = None  # Global reference for cleanup
_cleanup_done = False  # Prevent double cleanup

# --- Constants ---
SUPPORTED_EXTENSIONS = ('.wav', '.mp3')
DEFAULT_FREQUENCY = 44100
DEFAULT_BUFFER_SIZE = 512

# Mapping from Folder Name to MIDI Note
# Key1 -> 50, Key2 -> 51, etc.
NOTE_MAPPING = {
    "Key1": 50,
    "Key2": 51,
    "Key3": 52,
    "Key4": 53,
    "Key5": 54,
    "Key6": 55,
    "Key7": 56,
    "Key8": 57,
    "Key9": 58,
    "Key10": 59,
    "Key11": 60,
    "Key12": 61,
}

# Mapping from MIDI Note to Folder Name (Reverse lookup)
NOTE_TO_KEY = {v: k for k, v in NOTE_MAPPING.items()}
STOP_KEY_NAME = "Key1"


def cleanup_resources():
    """Cleanup function to release MIDI device. Safe to call multiple times."""
    global midi_port, _cleanup_done
    
    if _cleanup_done:
        return
    _cleanup_done = True
    
    print("\n[CLEANUP] Releasing resources...")
    
    # 1. Close MIDI port FIRST (most important)
    if midi_port is not None:
        try:
            midi_port.close()
            print("   [OK] MIDI port closed.")
        except Exception as e:
            print(f"   [WARN] MIDI port close error: {e}")
        midi_port = None
    
    # 2. Quit pygame.midi
    try:
        if pygame.midi.get_init():
            pygame.midi.quit()
            print("   [OK] pygame.midi released.")
    except Exception:
        pass
    
    # 3. Quit pygame.mixer  
    try:
        if pygame.mixer.get_init():
            pygame.mixer.quit()
            print("   [OK] pygame.mixer released.")
    except Exception:
        pass
    
    # 4. Full pygame quit
    try:
        pygame.quit()
    except Exception:
        pass
    
    print("[CLEANUP] Complete - MIDI device should be free now.")


def signal_handler(signum, frame):
    """Handle termination signals to ensure cleanup runs."""
    signal_name = signal.Signals(signum).name if hasattr(signal, 'Signals') else str(signum)
    print(f"\n[SIGNAL] Received {signal_name}, shutting down...")
    cleanup_resources()
    sys.exit(0)


def setup_signal_handlers():
    """Register signal handlers for clean shutdown."""
    # Handle Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)
    # Handle termination (Windows doesn't have SIGTERM in the same way)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, signal_handler)
    # Handle break (Windows Ctrl+Break)
    if hasattr(signal, 'SIGBREAK'):
        signal.signal(signal.SIGBREAK, signal_handler)


def initialize_audio():
    """Initializes pygame.mixer for audio playback."""
    global current_channel
    
    print("\n[INIT] Initializing Pygame Mixer...")
    try:
        # Initialize pygame first
        pygame.init()
        
        # Configure mixer for low-latency audio
        pygame.mixer.init(
            frequency=DEFAULT_FREQUENCY, 
            buffer=DEFAULT_BUFFER_SIZE
        )
        # Get a specific channel for controlled monophonic playback
        current_channel = pygame.mixer.Channel(0) 
        print(f"   [OK] Mixer ready: {DEFAULT_FREQUENCY}Hz, {DEFAULT_BUFFER_SIZE} buffer")
        return True
    except pygame.error as e:
        print(f"   [FAIL] Mixer error: {e}")
        return False


def initialize_midi():
    """Initializes MIDI and returns an open MIDI input port."""
    global midi_port
    
    print("\n[INIT] Initializing MIDI...")
    
    # Initialize pygame.midi
    if not pygame.midi.get_init():
        pygame.midi.init()
        print("   [OK] pygame.midi initialized")
    
    # List all MIDI devices
    print("\n[SCAN] MIDI Devices:")
    device_count = pygame.midi.get_count()
    
    input_devices = []
    for i in range(device_count):
        info = pygame.midi.get_device_info(i)
        name = info[1].decode('utf-8') if isinstance(info[1], bytes) else info[1]
        is_input = info[2]
        is_opened = info[4]
        device_type = "INPUT" if is_input else "OUTPUT"
        status = "[LOCKED]" if is_opened else ""
        print(f"   [{i}] {name} ({device_type}) {status}")
        
        if is_input and not is_opened:
            input_devices.append((i, name))
    
    if not input_devices:
        print("\n   [FAIL] No available MIDI input devices!")
        return None
    
    # Use pygame.midi directly (more reliable on Windows)
    print("\n   Opening MIDI input...")
    for device_id, device_name in input_devices:
        try:
            pygame_input = pygame.midi.Input(device_id)
            print(f"   [OK] Opened: {device_name}")
            return PygameMidiWrapper(pygame_input, device_name)
        except Exception as e:
            print(f"   [FAIL] {e}")
    
    return None


class PygameMidiWrapper:
    """Wrapper to make pygame.midi.Input compatible with mido interface."""
    
    def __init__(self, pygame_input, name):
        self._input = pygame_input
        self.name = name
        self._closed = False
    
    def poll(self):
        """Poll for MIDI messages."""
        if self._closed:
            return None
        try:
            if self._input.poll():
                events = self._input.read(1)
                if events:
                    midi_data = events[0][0]
                    status = midi_data[0]
                    data1 = midi_data[1]
                    data2 = midi_data[2]
                    
                    msg_type = status & 0xF0
                    channel = status & 0x0F
                    
                    if msg_type == 0x90:  # Note On
                        return MidiMessage('note_on', note=data1, velocity=data2, channel=channel)
                    elif msg_type == 0x80:  # Note Off
                        return MidiMessage('note_off', note=data1, velocity=data2, channel=channel)
        except Exception as e:
            print(f"[ERROR] MIDI poll error: {e}")
        return None
    
    def close(self):
        """Close the MIDI input."""
        if not self._closed:
            self._closed = True
            try:
                self._input.close()
            except Exception:
                pass


class MidiMessage:
    """Simple MIDI message class compatible with mido messages."""
    
    def __init__(self, msg_type, **kwargs):
        self.type = msg_type
        for key, value in kwargs.items():
            setattr(self, key, value)


def get_default_uploads_dir():
    """Find the uploads directory relative to this script."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    potential_path = os.path.join(script_dir, "uploads")
    if os.path.isdir(potential_path):
        return potential_path
    return None


def get_sample_folder_path(args_path=None):
    """Determines the sample folder path."""
    if args_path and os.path.isdir(args_path):
        return args_path

    default_path = get_default_uploads_dir()
    if default_path:
        print(f"\n[AUTO] Found uploads: {default_path}")
        return default_path

    while True:
        folder_path = input("\nEnter path to audio samples folder: ").strip()
        if os.path.isdir(folder_path):
            return folder_path
        print(f"Invalid path: '{folder_path}'")


class SampleLoader:
    """Handles loading and hot-reloading of samples."""
    
    def __init__(self, folder_path):
        self.folder_path = folder_path
        self.samples = {}  # {midi_note: pygame.mixer.Sound}
        self._file_cache = {}  # {midi_note: (file_path, mtime)}
        self._last_scan_time = 0
        self.scan_interval = 2.0  # Seconds between scans

    def scan_and_update(self):
        """Scans directories and updates samples if changes detected."""
        current_time = time.time()
        if current_time - self._last_scan_time < self.scan_interval:
            return False
            
        self._last_scan_time = current_time
        changes_detected = False

        for key_folder, midi_note in NOTE_MAPPING.items():
            target_dir = os.path.join(self.folder_path, key_folder)
            
            # Find the valid audio file
            current_file = None
            current_mtime = 0
            
            if os.path.isdir(target_dir):
                try:
                    # Get all valid files with stats
                    valid_files = []
                    for f in os.listdir(target_dir):
                        if f.lower().endswith(SUPPORTED_EXTENSIONS):
                            full_path = os.path.join(target_dir, f)
                            valid_files.append((full_path, os.path.getmtime(full_path)))
                    
                    # Sort to ensure deterministic selection (e.g. alphabetical)
                    valid_files.sort(key=lambda x: x[0])
                    
                    if valid_files:
                        current_file, current_mtime = valid_files[0]
                except OSError:
                    pass

            # Check if we need to update
            cached_info = self._file_cache.get(midi_note)
            
            # Case 1: New file or file changed
            if current_file:
                if (not cached_info) or (cached_info[0] != current_file) or (cached_info[1] != current_mtime):
                    try:
                        print(f"[RELOAD] Loading {key_folder}: {os.path.basename(current_file)}")
                        sound = pygame.mixer.Sound(current_file)
                        self.samples[midi_note] = sound
                        self._file_cache[midi_note] = (current_file, current_mtime)
                        changes_detected = True
                    except (pygame.error, OSError) as e:
                        print(f"[ERROR] Failed to load {current_file}: {e}")
            
            # Case 2: File removed
            elif cached_info:
                print(f"[REMOVE] Unloaded sample for {key_folder}")
                self.samples.pop(midi_note, None)
                self._file_cache.pop(midi_note, None)
                changes_detected = True

        return changes_detected

    def get_sample(self, midi_note):
        return self.samples.get(midi_note)


def handle_midi_message(msg, loader):
    """Processes incoming MIDI messages."""
    global current_channel
    
    if msg.type not in ['note_on', 'note_off']:
        return

    midi_note = msg.note
    
    if msg.type == 'note_on' and msg.velocity > 0:
        if midi_note in NOTE_TO_KEY:
            key_name = NOTE_TO_KEY[midi_note]

            # STOP COMMAND
            if key_name == STOP_KEY_NAME:
                if current_channel and current_channel.get_busy():
                    current_channel.stop()
                print(f"[STOP] {key_name}")
                return

            # PLAY COMMAND
            sound = loader.get_sample(midi_note)
            if sound:
                if current_channel and current_channel.get_busy():
                    current_channel.stop()
                current_channel.play(sound)
                print(f"[PLAY] {key_name} (Note {midi_note}, Vel: {msg.velocity})")
            else:
                print(f"[SKIP] {key_name} - no sample")
        else:
            print(f"[SKIP] Note {midi_note} - not mapped")


def main():
    """Main function to run the MIDI sampler."""
    global midi_port
    
    # Setup signal handlers FIRST
    setup_signal_handlers()
    
    parser = argparse.ArgumentParser(description="MIDI Sampler for Piano Player")
    parser.add_argument("--dir", help="Path to uploads directory", default=None)
    args = parser.parse_args()

    print("=" * 50)
    print("       MIDI SAMPLER - Piano Player")
    print("=" * 50)
    
    try:
        # 1. Initialize Audio
        if not initialize_audio():
            print("\n[ERROR] Failed to initialize audio!")
            cleanup_resources()
            sys.exit(1)
            
        # 2. Initialize MIDI
        midi_port = initialize_midi()
        
        if midi_port is None:
            print("\n" + "=" * 50)
            print("[ERROR] No MIDI device available!")
            print("=" * 50)
            print("\nTroubleshooting:")
            print("1. Make sure MIDI controller is connected")
            print("2. Close other apps using MIDI (DAWs, etc.)")
            print("3. Run: python reset_midi.py")
            print("4. Unplug/replug MIDI device")
            cleanup_resources()
            sys.exit(1)
        
        # 3. Load Samples (Initial Scan)
        folder_path = get_sample_folder_path(args.dir)
        loader = SampleLoader(folder_path)
        loader.scan_and_update()  # Initial load
        
        if not loader.samples:
            print("\n[WARN] No samples loaded initially!")

        # 4. Main Loop
        print("\n" + "=" * 50)
        print("*** READY - Waiting for MIDI input ***")
        print("=" * 50)
        print(f"Device: {getattr(midi_port, 'name', 'Unknown')}")
        print("Hot-reloading enabled: Checking for new files every 2s")
        print("Press Ctrl+C to quit.\n")
        
        while True:
            try:
                # Poll MIDI
                msg = midi_port.poll()
                if msg:
                    handle_midi_message(msg, loader)
                
                # Check for file updates
                loader.scan_and_update()
                    
                time.sleep(0.001)
            except Exception as e:
                print(f"[ERROR] Main loop error: {e}")
                time.sleep(0.1)  # Avoid tight error loop

    except KeyboardInterrupt:
        print("\n[EXIT] User interrupt.")
    except Exception as e:
        print(f"\n[FATAL] {e}")
        import traceback
        traceback.print_exc()
    finally:
        # ALWAYS cleanup, no matter what
        cleanup_resources()


if __name__ == '__main__':
    main()