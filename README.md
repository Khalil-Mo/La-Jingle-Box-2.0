# La Jingle Box 2.0

A MIDI-controlled audio sampler with a web interface for managing samples.

## Features

- 🎹 **MIDI Input**: Trigger audio samples from your MIDI controller
- 🌐 **Web Interface**: Upload and manage samples via browser
- 🔄 **Hot-Reloading**: Detects new sample files automatically
- 💾 **Supports**: WAV and MP3 audio formats

## Requirements

```bash
# Python
pip install pygame mido

# Node.js (for web interface)
cd piano-upload && npm install
```

## Quick Start

```bash
python run.py
```

This will:
1. Start the web interface server
2. Open your browser to http://localhost:3000
3. Start the MIDI sampler

Press **Ctrl+C** to stop everything.

## MIDI Key Mapping

| Folder   | MIDI Note | Function   |
|----------|-----------|------------|
| `Key1`   | 50        | **STOP**   |
| `Key2`   | 51        | Play       |
| `Key3`   | 52        | Play       |
| `Key4`   | 53        | Play       |
| `Key5`   | 54        | Play       |
| `Key6`   | 55        | Play       |
| `Key7`   | 56        | Play       |
| `Key8`   | 57        | Play       |
| `Key9`   | 58        | Play       |
| `Key10`  | 59        | Play       |
| `Key11`  | 60        | Play       |
| `Key12`  | 61        | Play       |

## Folder Structure

```
La-Jingle-Box-2.0/
├── midi_sampler.py       # Main MIDI sampler script
├── reset_midi.py         # MIDI device reset utility
├── sounds/               # Additional sound files
└── piano-upload/
    ├── server.js         # Web upload server
    ├── public/           # Web interface files
    └── uploads/          # Sample storage
        ├── Key1/         # Audio files for MIDI note 50
        ├── Key2/         # Audio files for MIDI note 51
        └── ...           # etc.
```

## Adding Samples

### Via Web Interface
1. Start the web server: `node piano-upload/server.js`
2. Go to http://localhost:3000
3. Select a key and upload your audio file (.wav or .mp3)

### Manually
Place audio files directly in the corresponding `piano-upload/uploads/KeyX/` folder. The sampler will detect new files automatically.

## Troubleshooting

### MIDI Device Not Found or Locked

If you see "No MIDI device available" or the device shows as locked:

1. **Close other applications** using MIDI (DAWs, MIDI monitors, etc.)
2. **Run the reset utility**:
   ```bash
   python reset_midi.py
   ```
3. **Unplug and replug** your MIDI device
4. **Restart your computer** if issues persist

### Custom Sample Directory

You can specify a custom sample directory:
```bash
python midi_sampler.py --dir "C:/path/to/your/samples"
```

## Building an Executable

To create a standalone `.exe` file:

```bash
pyinstaller --onefile --add-data "C:/Users/momoc/AppData/Local/Programs/Python/Python313/Lib/site-packages/pygame;pygame" --hidden-import=mido --hidden-import=pygame --hidden-import=mido.backends.pygame midi_sampler.py
```

> **Note**: Adjust the pygame path to match your Python installation.

The executable will be created in the `dist/` folder.

## Controls

- **Ctrl+C**: Quit the sampler cleanly
- **Key1 (MIDI 50)**: Stop current playback
- **Key2-Key12 (MIDI 51-61)**: Play assigned samples

---

Made with ♪ for live performances and jingle playback.
