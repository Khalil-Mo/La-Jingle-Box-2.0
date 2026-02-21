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
import socket

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

# OLED Display (optional)
try:
    from luma.core.interface.serial import i2c
    from luma.oled.device import ssd1306
    from PIL import Image, ImageDraw, ImageFont
    OLED_AVAILABLE = True
except ImportError:
    OLED_AVAILABLE = False


# --- Global State ---
current_channel = None
midi_port = None  # Global reference for cleanup
_cleanup_done = False  # Prevent double cleanup
oled = None  # Global reference for OLED display
amp_pin = None  # GPIO pin number for amplifier enable (None = disabled)

# --- Constants ---
SUPPORTED_EXTENSIONS = ('.wav', '.mp3')
DEFAULT_FREQUENCY = 44100
DEFAULT_BUFFER_SIZE = 2048

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

# Default GPIO for amplifier SD pin: PC9 = (2 * 32) + 9 = 73
DEFAULT_AMP_GPIO = 73


def gpio_export(pin):
    """Export a GPIO pin via sysfs and configure as output LOW."""
    try:
        with open("/sys/class/gpio/export", "w") as f:
            f.write(str(pin))
    except OSError:
        pass  # already exported
    with open(f"/sys/class/gpio/gpio{pin}/direction", "w") as f:
        f.write("out")
    with open(f"/sys/class/gpio/gpio{pin}/value", "w") as f:
        f.write("0")


def gpio_set(pin, value):
    """Set a GPIO pin HIGH (1) or LOW (0)."""
    with open(f"/sys/class/gpio/gpio{pin}/value", "w") as f:
        f.write(str(value))


def gpio_unexport(pin):
    """Unexport a GPIO pin."""
    try:
        with open("/sys/class/gpio/unexport", "w") as f:
            f.write(str(pin))
    except OSError:
        pass


def cleanup_resources():
    """Cleanup function to release MIDI device. Safe to call multiple times."""
    global midi_port, _cleanup_done, oled, amp_pin

    if _cleanup_done:
        return
    _cleanup_done = True

    print("\n[CLEANUP] Releasing resources...")

    # 1. Disable amplifier FIRST (before audio shutdown to avoid pop)
    if amp_pin is not None:
        try:
            gpio_set(amp_pin, 0)
            print("   [OK] Amplifier disabled.")
        except Exception:
            pass

    # 2. Close MIDI port
    if midi_port is not None:
        try:
            midi_port.close()
            print("   [OK] MIDI port closed.")
        except Exception as e:
            print(f"   [WARN] MIDI port close error: {e}")
        midi_port = None

    # 3. Quit pygame.midi
    try:
        if pygame.midi.get_init():
            pygame.midi.quit()
            print("   [OK] pygame.midi released.")
    except Exception:
        pass

    # 4. Quit pygame.mixer
    try:
        if pygame.mixer.get_init():
            pygame.mixer.quit()
            print("   [OK] pygame.mixer released.")
    except Exception:
        pass

    # 5. Full pygame quit
    try:
        pygame.quit()
    except Exception:
        pass

    # 6. Release amplifier GPIO
    if amp_pin is not None:
        try:
            gpio_unexport(amp_pin)
            print("   [OK] Amplifier GPIO released.")
        except Exception:
            pass
        amp_pin = None

    # 7. Clear OLED display
    if oled is not None:
        try:
            oled.clear()
            print("   [OK] OLED cleared.")
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


class OledDisplay:
    """Drives a 128x64 dual-color SSD1306 OLED over I2C.

    Display zones:
      - Yellow area: top 16 pixels  → always shows "CarlBox v2"
      - Blue area:   bottom 48 pixels → progress bar or IP + status
    """

    WIDTH = 128
    HEIGHT = 64
    YELLOW_H = 16  # top yellow zone
    BLUE_Y = 16    # blue zone starts here

    # Common font search paths across Linux distros
    _BOLD_FONTS = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    ]
    _REGULAR_FONTS = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ]

    @staticmethod
    def _load_font(paths, size):
        """Try each font path, fall back to Pillow default at given size."""
        for path in paths:
            try:
                return ImageFont.truetype(path, size)
            except (IOError, OSError):
                continue
        # Pillow >= 10.0 supports sized default
        try:
            return ImageFont.load_default(size=size)
        except TypeError:
            return ImageFont.load_default()

    def __init__(self, bus=2, address=0x3C, web_port=80):
        serial = i2c(port=bus, address=address)
        self.device = ssd1306(serial)

        self.font_title = self._load_font(self._BOLD_FONTS, 16)
        self.font_bold = self._load_font(self._BOLD_FONTS, 14)
        self.font = self._load_font(self._REGULAR_FONTS, 14)

        self._ip = self._get_ip()
        self._web_port = web_port
        self._status = "Ready"

    @staticmethod
    def _get_ip():
        """Get a real (non-loopback) IP address, or None if unavailable."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            if ip and not ip.startswith("127."):
                return ip
        except Exception:
            pass
        return None

    def _draw_title(self, draw):
        """Draw 'CarlBox v2' centered in the yellow zone (top 16px)."""
        text = "CarlBox v2"
        bbox = draw.textbbox((0, 0), text, font=self.font_title)
        tw = bbox[2] - bbox[0]
        x = (self.WIDTH - tw) // 2
        draw.text((x, -1), text, fill=1, font=self.font_title)

    def _center_text(self, draw, y, text, font=None):
        """Draw text horizontally centered at given y."""
        font = font or self.font
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        x = (self.WIDTH - tw) // 2
        draw.text((x, y), text, fill=1, font=font)

    def show_splash(self):
        """Show splash: title in yellow, empty blue area."""
        img = Image.new("1", (self.WIDTH, self.HEIGHT), 0)
        draw = ImageDraw.Draw(img)
        self._draw_title(draw)
        self.device.display(img)

    def show_progress(self, label, percent):
        """Show title + progress bar with label in blue area."""
        img = Image.new("1", (self.WIDTH, self.HEIGHT), 0)
        draw = ImageDraw.Draw(img)

        # Yellow zone: title
        self._draw_title(draw)

        # Blue zone: label + progress bar
        self._center_text(draw, self.BLUE_Y + 4, label)

        bar_x, bar_w, bar_h = 4, 120, 10
        bar_y = self.BLUE_Y + 26
        draw.rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], outline=1)

        fill_w = int(bar_w * min(percent, 100) / 100)
        if fill_w > 0:
            draw.rectangle([bar_x, bar_y, bar_x + fill_w, bar_y + bar_h], fill=1)

        self.device.display(img)

    def set_status(self, status):
        """Update status line and refresh display."""
        self._status = status
        self._render()

    def _render(self):
        """Redraw: title in yellow, IP + status centered in blue."""
        img = Image.new("1", (self.WIDTH, self.HEIGHT), 0)
        draw = ImageDraw.Draw(img)

        # Yellow zone: title
        self._draw_title(draw)

        # Blue zone: IP (regular) + status (bold), vertically centered
        if self._ip:
            ip_line = self._ip if self._web_port == 80 else f"{self._ip}:{self._web_port}"
        else:
            ip_line = "No IP address !"
        self._center_text(draw, self.BLUE_Y + 8, ip_line)
        self._center_text(draw, self.BLUE_Y + 28, self._status, font=self.font_bold)

        self.device.display(img)

    def clear(self):
        """Turn off the display."""
        try:
            self.device.hide()
        except Exception:
            pass


def get_default_uploads_dir():
    """Find the piano-upload/uploads directory relative to this script."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    potential_path = os.path.join(script_dir, "piano-upload", "uploads")
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

    def count_samples(self):
        """Count how many sample files exist (fast scan, no loading)."""
        count = 0
        for key_folder in NOTE_MAPPING:
            target_dir = os.path.join(self.folder_path, key_folder)
            if os.path.isdir(target_dir):
                try:
                    for f in os.listdir(target_dir):
                        if f.lower().endswith(SUPPORTED_EXTENSIONS):
                            count += 1
                            break  # one sample per key
                except OSError:
                    pass
        return count

    def _find_sample_file(self, key_folder):
        """Find the audio file for a key folder. Returns (path, mtime) or (None, 0)."""
        target_dir = os.path.join(self.folder_path, key_folder)
        if not os.path.isdir(target_dir):
            return None, 0
        try:
            valid_files = []
            for f in os.listdir(target_dir):
                if f.lower().endswith(SUPPORTED_EXTENSIONS):
                    full_path = os.path.join(target_dir, f)
                    valid_files.append((full_path, os.path.getmtime(full_path)))
            valid_files.sort(key=lambda x: x[0])
            if valid_files:
                return valid_files[0]
        except OSError:
            pass
        return None, 0

    def scan_and_update(self, on_progress=None):
        """Scans directories and updates samples if changes detected.

        Args:
            on_progress: optional callback(loaded_index, total) called after
                         each key is processed. Only used during initial load.
        """
        current_time = time.time()
        if on_progress is None and current_time - self._last_scan_time < self.scan_interval:
            return False

        self._last_scan_time = current_time
        changes_detected = False
        items = list(NOTE_MAPPING.items())
        total = len(items)

        for idx, (key_folder, midi_note) in enumerate(items):
            current_file, current_mtime = self._find_sample_file(key_folder)
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

            if on_progress:
                on_progress(idx + 1, total)

        return changes_detected

    def get_sample(self, midi_note):
        return self.samples.get(midi_note)


def handle_midi_message(msg, loader, oled=None):
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
                if oled:
                    oled.set_status("Ready")
                return

            # PLAY COMMAND
            sound = loader.get_sample(midi_note)
            if sound:
                if current_channel and current_channel.get_busy():
                    current_channel.stop()
                current_channel.play(sound)
                print(f"[PLAY] {key_name} (Note {midi_note}, Vel: {msg.velocity})")
                if oled:
                    oled.set_status(f"Playing {key_name}")
            else:
                print(f"[SKIP] {key_name} - no sample")
        else:
            print(f"[SKIP] Note {midi_note} - not mapped")


def main(pre_load_hook=None):
    """Main function to run the MIDI sampler.

    Args:
        pre_load_hook: Optional callable to run before loading samples
                       (e.g. starting the web server from run.py).
    """
    global midi_port, amp_pin

    # Setup signal handlers FIRST
    setup_signal_handlers()
    
    parser = argparse.ArgumentParser(description="MIDI Sampler for Piano Player")
    parser.add_argument("--dir", help="Path to uploads directory", default=None)
    parser.add_argument("--i2c-bus", type=int, default=2,
                        help="I2C bus number for OLED display (default: 2)")
    parser.add_argument("--i2c-addr", type=lambda x: int(x, 0), default=0x3C,
                        help="I2C address for OLED display (default: 0x3C)")
    parser.add_argument("--no-oled", action="store_true",
                        help="Disable OLED display")
    parser.add_argument("--amp-pin", type=int, default=DEFAULT_AMP_GPIO,
                        help=f"GPIO pin for amplifier enable/SD (default: {DEFAULT_AMP_GPIO} = PC9)")
    parser.add_argument("--no-amp", action="store_true",
                        help="Disable amplifier GPIO control")
    args = parser.parse_args()

    print("=" * 50)
    print("       MIDI SAMPLER - Piano Player")
    print("=" * 50)
    
    try:
        # 1. Initialize OLED Display (first, so we can show splash/progress)
        oled = None
        if OLED_AVAILABLE and not args.no_oled:
            try:
                oled = OledDisplay(bus=args.i2c_bus, address=args.i2c_addr)
                print(f"   [OK] OLED display on /dev/i2c-{args.i2c_bus} @ {hex(args.i2c_addr)}")
                oled.show_splash()
                time.sleep(1.5)
            except Exception as e:
                print(f"   [WARN] OLED not available: {e}")
                oled = None
        elif not OLED_AVAILABLE:
            print("   [INFO] luma.oled not installed, OLED disabled")

        # 2. Setup amplifier GPIO (keep disabled during audio init)
        if oled:
            oled.show_progress("Init hardware...", 4)
        if not args.no_amp:
            try:
                gpio_export(args.amp_pin)
                amp_pin = args.amp_pin
                print(f"   [OK] Amplifier GPIO {amp_pin} ready (disabled)")
            except Exception as e:
                print(f"   [WARN] Amplifier GPIO not available: {e}")
                amp_pin = None

        # 3. Initialize Audio
        if oled:
            oled.show_progress("Init audio...", 8)
        if not initialize_audio():
            print("\n[ERROR] Failed to initialize audio!")
            cleanup_resources()
            sys.exit(1)

        # Enable amplifier now that audio is settled
        if amp_pin is not None:
            time.sleep(0.1)  # brief settle time
            gpio_set(amp_pin, 1)
            print("   [OK] Amplifier enabled.")

        # 4. Initialize MIDI
        if oled:
            oled.show_progress("Init MIDI...", 11)
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

        # 5. Run pre-load hook (e.g. start web server)
        if pre_load_hook:
            if oled:
                oled.show_progress("Init Web UI...", 15)
            pre_load_hook()

        # 6. Load Samples (20% to 100% of progress bar)
        if oled:
            oled.show_progress("Loading samples...", 20)
        folder_path = get_sample_folder_path(args.dir)
        loader = SampleLoader(folder_path)

        def _on_sample_progress(loaded, total):
            if oled:
                pct = 20 + int(80 * loaded / total)
                oled.show_progress(f"Loading {loaded}/{total}", pct)

        loader.scan_and_update(on_progress=_on_sample_progress)

        if not loader.samples:
            print("\n[WARN] No samples loaded initially!")

        if oled:
            oled.show_progress("Ready!", 100)
            time.sleep(0.5)
            oled.set_status("Ready")

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
                    handle_midi_message(msg, loader, oled)
                
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