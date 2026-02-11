# CarlBox BLE Mobile App — Design Document

## Context

CarlBox is an OrangePi Zero 3-based audio sampler. Users upload MP3 samples and trigger them with an Akai LPK25 MIDI keyboard. The current UX requires connecting to a WiFi hotspot and using a browser. This design replaces that with a native iOS app communicating over Bluetooth Low Energy.

## Architecture

```
┌──────────────┐        BLE         ┌──────────────────────┐
│   iPhone     │◄──────────────────►│   OrangePi Zero 3    │
│              │                    │                      │
│  SwiftUI +   │   GATT Services    │  Python BLE server   │
│  CoreBluetooth│                   │  + MIDI sampler      │
└──────────────┘                    └──────────────────────┘
```

- **OrangePi**: single Python process running a BLE GATT peripheral (`bless`) + MIDI sampler (merged from existing `midi_sampler.py`)
- **iPhone**: native Swift/SwiftUI app using CoreBluetooth
- **Node.js piano-upload server is removed entirely** — no WiFi, no web UI
- Samples stored as compressed MP3 in `uploads/Key1/` through `uploads/Key12/`

## BLE GATT Protocol

The OrangePi advertises as a BLE peripheral with a custom GATT service. The iPhone discovers it by service UUID.

### Service: CarlBox Sample Manager

UUID: `CB000001-CARL-B0X0-0000-000000000000` (custom 128-bit)

### Characteristics

| Characteristic    | UUID     | Ops           | Purpose                                                   |
|-------------------|----------|---------------|-----------------------------------------------------------|
| **File List**     | CB000002 | Read, Notify  | Returns JSON list of samples per key. Notifies on changes |
| **File Transfer** | CB000003 | Write         | Receives MP3 file data in ~512-byte chunks                |
| **File Command**  | CB000004 | Write         | Commands: delete a file, set target key for upload        |
| **Transfer Status**| CB000005| Read, Notify  | Transfer progress/completion/error feedback               |

### Upload Flow

1. App writes to **File Command**: `{"action": "upload", "key": "Key5", "filename": "kick.mp3", "size": 45000}`
2. App writes MP3 data in sequential ~512-byte chunks to **File Transfer**
3. OrangePi acknowledges via **Transfer Status** after each chunk
4. On final chunk, OrangePi writes the assembled file to `uploads/Key5/kick.mp3`
5. **File List** notifies the app of the updated file list
6. MIDI sampler hot-reloads the new sample automatically

### Delete Flow

1. App writes to **File Command**: `{"action": "delete", "key": "Key5", "filename": "kick.mp3"}`
2. OrangePi deletes the file, notifies via **File List**

## iOS App — Screens & UX

Three screens, no settings, no login, no onboarding.

### 1. Connect Screen

- Scans for BLE devices advertising the CarlBox service UUID
- Shows a "CarlBox" card when discovered, with signal strength
- Tap to connect, spinner while pairing
- Auto-reconnects if previously paired

### 2. Keyboard View (main screen)

- Visual representation of the Akai LPK25 (25-key keyboard with white and black keys)
- 12 mapped keys (MIDI 50-61, D3 to C#4) are highlighted and tappable, showing assigned sample filenames
- Remaining 13 keys are dimmed/inactive
- Key1 (D3, MIDI 50) is visually distinct (red) — this is the STOP key
- Black keys (D#3, F#3, G#3, A#3, C#4) rendered shorter and raised, like the real keyboard
- Landscape orientation for proper keyboard proportions
- Tap an active key to open Key Detail

### MIDI Note Mapping

| Key   | MIDI Note | Piano Note | Role   |
|-------|-----------|------------|--------|
| Key1  | 50        | D3         | STOP   |
| Key2  | 51        | D#3        | Sample |
| Key3  | 52        | E3         | Sample |
| Key4  | 53        | F3         | Sample |
| Key5  | 54        | F#3        | Sample |
| Key6  | 55        | G3         | Sample |
| Key7  | 56        | G#3        | Sample |
| Key8  | 57        | A3         | Sample |
| Key9  | 58        | A#3        | Sample |
| Key10 | 59        | B3         | Sample |
| Key11 | 60        | C4         | Sample |
| Key12 | 61        | C#4        | Sample |

### 3. Key Detail

- Shows the selected key (note name + MIDI number)
- Lists all samples assigned to that key (filename, file size)
- "Add Sample" button opens iOS file picker (Files app), filtered to .mp3
- Swipe-to-delete on each sample
- Upload progress bar during transfer

## OrangePi — Python BLE Server

Single Python process replaces both `midi_sampler.py` and the Node.js server.

### Responsibilities

- BLE GATT peripheral via `bless` (BlueZ D-Bus backend)
- MIDI input via `mido` with pygame.midi fallback
- Audio playback via `pygame.mixer`
- File management on `uploads/` directory
- Hot-reload: file changes on disk picked up by sampler automatically

### BLE Handlers

- `on_read(File List)` — scans `uploads/Key*/` and returns JSON
- `on_write(File Command)` — parses command, prepares upload buffer or deletes file
- `on_write(File Transfer)` — appends chunk to buffer, writes to disk when complete
- `on_read(Transfer Status)` — returns current transfer state

### Startup Sequence

1. Initialize pygame.mixer + MIDI input
2. Start BLE advertising as "CarlBox"
3. Enter main loop: handle BLE events + poll MIDI input
4. On shutdown (SIGTERM/SIGINT): stop advertising, cleanup MIDI, exit

## File Structure After Refactor

```
piano/
├── carlbox_server.py      # BLE GATT server + MIDI sampler (merged)
├── reset_midi.py          # kept as-is
├── requirements.txt       # bless, mido, pygame
├── docs/
│   └── plans/
│       └── 2026-02-11-ble-mobile-app-design.md
└── uploads/
    ├── Key1/ ... Key12/

CarlBoxApp/                # iOS Xcode project (new)
├── CarlBoxApp.swift
├── Views/
│   ├── ConnectView.swift
│   ├── KeyboardView.swift
│   └── KeyDetailView.swift
├── BLE/
│   └── BLEManager.swift
└── Models/
    └── Sample.swift
```

## Removed

- `piano-upload/` (Node.js server, web UI) — deleted
- `run.py` — replaced by `carlbox_server.py`
