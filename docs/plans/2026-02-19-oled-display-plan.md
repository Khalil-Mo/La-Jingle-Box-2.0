# OLED Display Integration — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add optional I2C OLED (SSD1306 128x64) display to `midi_sampler.py` showing status, now-playing, and scrolling log.

**Architecture:** A new `OledDisplay` class added directly to `midi_sampler.py`. The class wraps `luma.oled` device init and Pillow rendering. It is instantiated in `main()` and passed to functions that need it. If `luma.oled` is not installed or the display is not found, `oled` stays `None` and all display calls are skipped — zero impact on existing behavior.

**Tech Stack:** Python 3, `luma.oled` (SSD1306 driver), `luma.core` (I2C serial), `Pillow` (drawing/fonts)

---

### Task 1: Add OLED optional import and availability flag

**Files:**
- Modify: `midi_sampler.py:14-36` (imports section)

**Step 1: Add the conditional import block**

After the existing `pygame` import block (line 36), add:

```python
# OLED Display (optional)
try:
    from luma.core.interface.serial import i2c
    from luma.oled.device import ssd1306
    from PIL import Image, ImageDraw, ImageFont
    OLED_AVAILABLE = True
except ImportError:
    OLED_AVAILABLE = False
```

**Step 2: Verify script still starts without luma installed**

Run: `python midi_sampler.py --help`
Expected: Normal help output, no crash. `OLED_AVAILABLE` will be `False` if luma is not installed locally.

**Step 3: Commit**

```bash
git add midi_sampler.py
git commit -m "feat: add optional luma.oled import with graceful fallback"
```

---

### Task 2: Add CLI arguments for OLED configuration

**Files:**
- Modify: `midi_sampler.py:391-393` (argparse section in `main()`)

**Step 1: Add three new arguments after the existing `--dir` arg**

```python
parser.add_argument("--i2c-bus", type=int, default=2,
                    help="I2C bus number for OLED display (default: 2)")
parser.add_argument("--i2c-addr", type=lambda x: int(x, 0), default=0x3C,
                    help="I2C address for OLED display (default: 0x3C)")
parser.add_argument("--no-oled", action="store_true",
                    help="Disable OLED display")
```

**Step 2: Verify**

Run: `python midi_sampler.py --help`
Expected: Shows `--i2c-bus`, `--i2c-addr`, `--no-oled` in help output.

**Step 3: Commit**

```bash
git add midi_sampler.py
git commit -m "feat: add OLED CLI arguments (--i2c-bus, --i2c-addr, --no-oled)"
```

---

### Task 3: Implement the OledDisplay class

**Files:**
- Modify: `midi_sampler.py` — add new class after `MidiMessage` class (after line 251)

**Step 1: Add the OledDisplay class**

```python
class OledDisplay:
    """Drives a 128x64 SSD1306 OLED over I2C."""

    WIDTH = 128
    HEIGHT = 64
    LOG_MAX_LINES = 3

    def __init__(self, bus=2, address=0x3C):
        serial = i2c(port=bus, address=address)
        self.device = ssd1306(serial)
        self.font_small = ImageFont.load_default()
        try:
            self.font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
        except (IOError, OSError):
            self.font_large = self.font_small

        self._midi_device = ""
        self._sample_count = 0
        self._now_playing = None
        self._log_lines = []

    def set_status(self, midi_device="", sample_count=0):
        """Update persistent status fields."""
        self._midi_device = midi_device[:20]
        self._sample_count = sample_count
        self._render()

    def set_now_playing(self, key_name=None):
        """Update now-playing indicator. None means idle."""
        self._now_playing = key_name
        self._render()

    def add_log(self, line):
        """Append a log line (keeps last LOG_MAX_LINES)."""
        self._log_lines.append(line[:26])
        self._log_lines = self._log_lines[-self.LOG_MAX_LINES:]
        self._render()

    def update_sample_count(self, count):
        """Update sample count without full status refresh."""
        self._sample_count = count
        self._render()

    def _render(self):
        """Redraw the full display."""
        img = Image.new("1", (self.WIDTH, self.HEIGHT), 0)
        draw = ImageDraw.Draw(img)

        # --- Top: status (2 lines, y=0 and y=10) ---
        title = f"Jingle Box  {self._sample_count} smp"
        draw.text((0, 0), title, fill=1, font=self.font_small)

        if self._midi_device:
            draw.text((0, 10), self._midi_device, fill=1, font=self.font_small)

        # Separator
        draw.line([(0, 21), (self.WIDTH, 21)], fill=1)

        # --- Middle: now playing (y=24) ---
        if self._now_playing:
            label = f"> {self._now_playing}"
        else:
            label = "Ready"
        draw.text((4, 24), label, fill=1, font=self.font_large)

        # Separator
        draw.line([(0, 42), (self.WIDTH, 42)], fill=1)

        # --- Bottom: log lines (y=44, 53, 62 — 3 lines of 9px) ---
        for idx, line in enumerate(self._log_lines):
            draw.text((0, 44 + idx * 7), line, fill=1, font=self.font_small)

        self.device.display(img)

    def clear(self):
        """Turn off the display."""
        try:
            self.device.hide()
        except Exception:
            pass
```

**Step 2: Verify syntax**

Run: `python -c "import ast; ast.parse(open('midi_sampler.py').read()); print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add midi_sampler.py
git commit -m "feat: implement OledDisplay class with status, now-playing, and log rendering"
```

---

### Task 4: Add OLED global and initialization in main()

**Files:**
- Modify: `midi_sampler.py` — global state section (line 40-42) and `main()` function

**Step 1: Add oled to global state**

Add after `_cleanup_done = False`:

```python
oled = None  # OledDisplay instance (or None if unavailable)
```

**Step 2: Add OLED initialization in main()**

After MIDI initialization succeeds (after `midi_port = initialize_midi()` and the error check), add:

```python
        # 2b. Initialize OLED Display
        oled = None
        if OLED_AVAILABLE and not args.no_oled:
            try:
                oled = OledDisplay(bus=args.i2c_bus, address=args.i2c_addr)
                print(f"   [OK] OLED display on /dev/i2c-{args.i2c_bus} @ {hex(args.i2c_addr)}")
            except Exception as e:
                print(f"   [WARN] OLED not available: {e}")
                oled = None
        elif not OLED_AVAILABLE:
            print("   [INFO] luma.oled not installed, OLED disabled")
```

**Step 3: Commit**

```bash
git add midi_sampler.py
git commit -m "feat: add OLED initialization with error handling in main()"
```

---

### Task 5: Wire OLED into handle_midi_message()

**Files:**
- Modify: `midi_sampler.py` — `handle_midi_message()` function signature and body

**Step 1: Add `oled` parameter to function signature**

Change:
```python
def handle_midi_message(msg, loader):
```
To:
```python
def handle_midi_message(msg, loader, oled=None):
```

**Step 2: Add OLED calls after existing print statements**

After the STOP print (`print(f"[STOP] {key_name}")`), add:
```python
                if oled:
                    oled.set_now_playing(None)
                    oled.add_log(f"[STOP] {key_name}")
```

After the PLAY print (`print(f"[PLAY] {key_name} ...")`), add:
```python
                if oled:
                    oled.set_now_playing(key_name)
                    oled.add_log(f"[PLAY] {key_name}")
```

After the SKIP (no sample) print, add:
```python
                if oled:
                    oled.add_log(f"[SKIP] {key_name}")
```

**Step 3: Update the call site in main()**

Change:
```python
                    handle_midi_message(msg, loader)
```
To:
```python
                    handle_midi_message(msg, loader, oled)
```

**Step 4: Commit**

```bash
git add midi_sampler.py
git commit -m "feat: wire OLED display into MIDI message handling"
```

---

### Task 6: Wire OLED into sample loader and startup status

**Files:**
- Modify: `midi_sampler.py` — `main()` function

**Step 1: Update OLED status after initial sample scan**

After `loader.scan_and_update()` and the "no samples" warning, add:

```python
        if oled:
            device_name = getattr(midi_port, 'name', 'Unknown')
            oled.set_status(midi_device=device_name, sample_count=len(loader.samples))
```

**Step 2: Add OLED update in main loop after sample reload**

Change the existing sample reload call in the main loop from:
```python
                loader.scan_and_update()
```
To:
```python
                if loader.scan_and_update() and oled:
                    oled.update_sample_count(len(loader.samples))
```

**Step 3: Commit**

```bash
git add midi_sampler.py
git commit -m "feat: wire OLED into sample loader status and hot-reload updates"
```

---

### Task 7: Add OLED cleanup

**Files:**
- Modify: `midi_sampler.py` — `cleanup_resources()` function

**Step 1: Add OLED cleanup**

Add before the "Complete" print at the end of `cleanup_resources()`, after the `pygame.quit()` block:

```python
    # 5. Clear OLED display
    if oled is not None:
        try:
            oled.clear()
            print("   [OK] OLED cleared.")
        except Exception:
            pass
```

Also add `oled` to the global declaration at the top of `cleanup_resources()`:
```python
    global midi_port, _cleanup_done, oled
```

**Step 2: Commit**

```bash
git add midi_sampler.py
git commit -m "feat: clear OLED display on shutdown"
```

---

### Task 8: Update README with OLED documentation

**Files:**
- Modify: `README.md`

**Step 1: Add OLED section**

After the "## Requirements" section, add OLED as optional:

```markdown
### Optional: OLED Display

For I2C OLED display support (SSD1306, 128x64):

```bash
pip install luma.oled
```

### OLED CLI Options

```bash
python midi_sampler.py --i2c-bus 2 --i2c-addr 0x3C   # specify bus/address
python midi_sampler.py --no-oled                       # disable OLED
```
```

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add OLED display setup and CLI options to README"
```

---

### Task 9: End-to-end verification

**Step 1: Verify script starts without luma installed**

Run: `python midi_sampler.py --help`
Expected: Runs normally, shows all args including `--i2c-bus`, `--i2c-addr`, `--no-oled`.

**Step 2: Verify --no-oled flag works**

Run: `python midi_sampler.py --no-oled`
Expected: Starts normally (will fail on MIDI if no device, but OLED init is skipped).

**Step 3: Verify syntax is clean**

Run: `python -c "import ast; ast.parse(open('midi_sampler.py').read()); print('Syntax OK')"`
Expected: `Syntax OK`
