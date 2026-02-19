# OLED Display Integration Design

## Goal

Add I2C OLED (SSD1306, 128x64, 0.96") support to `midi_sampler.py` so the device shows live status and log output.

## Hardware

- Orange Pi (SBC) with I2C enabled
- SSD1306 0.96" 128x64 OLED on `/dev/i2c-2` at address `0x3C`

## Library Choice

**`luma.oled`** (`pip install luma.oled`) — mature, Pillow-based rendering, works across SBC variants.

## Display Layout (128x64)

```
+----------------------------+
| La Jingle Box     12 smp   |  <- Status: title + loaded sample count
| MIDI: USB Keystation       |  <- Status: MIDI device name (truncated)
|----------------------------|
|    > Key5                  |  <- Now playing (larger text), or "Ready"
|----------------------------|
| [PLAY] Key5 (Note 54)     |  <- Log line 1 (most recent)
| [STOP] Key1               |  <- Log line 2
| [RELOAD] Key3: jingle.wav |  <- Log line 3
+----------------------------+
```

- Top 2 lines: persistent status (small font)
- Middle: current action / now playing (larger font)
- Bottom 3 lines: scrolling event log (small font)

## Architecture

### OledDisplay class

New class in `midi_sampler.py` that:
- Initializes the SSD1306 device via `luma.core.interface.serial.i2c`
- Uses Pillow (`PIL.ImageDraw`, `PIL.ImageFont`) for rendering
- Exposes methods: `show_status()`, `show_now_playing()`, `add_log_line()`, `render()`, `clear()`
- Keeps an internal log buffer (last 3 lines)
- Renders on event, not on timer

### Integration points

1. `initialize_midi()` success -> `oled.show_status(device_name, sample_count)`
2. `handle_midi_message()` PLAY -> `oled.show_now_playing(key_name)` + `oled.add_log_line(...)`
3. `handle_midi_message()` STOP -> `oled.show_now_playing(None)` + `oled.add_log_line(...)`
4. `SampleLoader.scan_and_update()` changes -> `oled.add_log_line(...)` + update sample count
5. `cleanup_resources()` -> `oled.clear()`

### Graceful degradation

```python
try:
    from luma.core.interface.serial import i2c
    from luma.oled.device import ssd1306
    OLED_AVAILABLE = True
except ImportError:
    OLED_AVAILABLE = False
```

If unavailable, `oled` is `None` and all calls are skipped. No impact on existing functionality.

### CLI args

- `--i2c-bus` (default: `2`) — I2C bus number
- `--i2c-addr` (default: `0x3C`) — I2C address (hex)
- `--no-oled` — disable OLED explicitly

## Dependencies

- `luma.oled` (brings in `luma.core`, `Pillow`, `smbus2`)
- Install: `pip install luma.oled`
