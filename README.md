# CarlBox v2

A MIDI-controlled audio sampler built on an Orange Pi Zero3, with a web interface for managing samples and a 0.96" OLED status display.

## Features

- MIDI input: trigger audio samples from a MIDI controller
- Web interface: upload and manage samples via browser (port 80)
- Hot-reloading: detects new sample files automatically
- OLED display: shows IP address, loading progress, and playback status
- Amplifier control: GPIO-controlled PAM8302A with spike-free startup
- Auto-start: runs as a systemd service on boot
- Supports WAV and MP3 audio formats

## Hardware

| Component | Model | Connection |
|-----------|-------|------------|
| Board | Orange Pi Zero3 (2GB) | - |
| OLED Display | 0.96" SSD1306 128x64 (yellow+blue) | I2C bus 2, addr 0x3C |
| Amplifier | PAM8302A | SD pin on GPIO PC9 (pin 73) |
| MIDI Controller | Any USB MIDI keyboard | USB |
| Audio Output | 3.5mm jack via onboard codec | card 0: audiocodec |

### Wiring

**OLED Display (I2C):**
| OLED Pin | Orange Pi Pin |
|----------|---------------|
| VCC | 3.3V |
| GND | GND |
| SDA | I2C3-SDA (PH5) |
| SCL | I2C3-SCL (PH4) |

**PAM8302A Amplifier:**
| PAM8302A Pin | Connection |
|--------------|------------|
| VIN | 5V |
| GND | GND |
| SD (enable) | GPIO PC9 (pin 73) |
| A+ | 3.5mm audio left/right |
| A- | 3.5mm audio ground |

## Full Setup Guide (Armbian)

### 1. Flash Armbian

Download Armbian for Orange Pi Zero3 from [armbian.com](https://www.armbian.com/orangepi-zero3/) and flash it to a microSD card using [balenaEtcher](https://etcher.balena.io/) or `dd`.

### 2. First boot: connect via Ethernet

Plug an Ethernet cable between the Orange Pi and your router. Power on the board, wait ~1 minute, then find its IP address from your router's admin page (look for `orangepi` or `carlboxv2`).

Connect via SSH:

```bash
ssh root@<ip-address>
```

Default root password is set on first boot. Follow the prompts to create a regular user account (e.g. `carlbox`).

### 3. Set up WiFi

Run the Armbian configuration tool:

```bash
armbian-config
```

Navigate to **Network > WiFi**, select your network and enter the password. This creates a netplan config in `/etc/netplan/` using `systemd-networkd`.

Once WiFi is connected, you can disconnect the Ethernet cable. Find the new WiFi IP:

```bash
ip addr show wlan0 | grep "inet "
```

Reconnect via SSH on the WiFi IP.

### 4. Enable I2C overlay

Run `armbian-config`, go to **System > Hardware** and enable the `i2c3-ph` overlay. This adds I2C bus 2 on pins PH4/PH5.

Reboot:

```bash
reboot
```

After reboot, verify the I2C bus and OLED display:

```bash
sudo apt install -y i2c-tools
i2cdetect -y 2
```

You should see `3c` in the output grid.

### 5. Install system dependencies

```bash
sudo apt update
sudo apt install -y python3 python3-venv git i2c-tools fonts-dejavu-core nodejs npm
```

### 6. Clone the project

```bash
sudo git clone https://github.com/Khalil-Mo/La-Jingle-Box-2.0.git /usr/src/carlbox-sampler
cd /usr/src/carlbox-sampler
sudo git checkout feat/oled-display
```

### 7. Set up Python virtual environment

```bash
cd /usr/src/carlbox-sampler
sudo python3 -m venv venv
sudo venv/bin/pip install pygame mido luma.oled
```

### 8. Install Node.js dependencies (web interface)

The web interface uses Express and Multer (defined in `piano-upload/package.json`):

```bash
cd /usr/src/carlbox-sampler/piano-upload
sudo npm install
```

### 9. Test manually

```bash
cd /usr/src/carlbox-sampler
sudo venv/bin/python run.py
```

You should see:
- Web server starting on port 80
- OLED splash screen ("CarlBox v2") with progress bar
- Audio and MIDI initialization
- "READY - Waiting for MIDI input"

Open `http://<orangepi-ip>` in a browser to access the upload interface.

Press **Ctrl+C** to stop everything.

### 10. Install the systemd service

```bash
sudo ln -sf /usr/src/carlbox-sampler/carlbox-sampler.service /etc/systemd/system/carlbox-sampler.service
sudo systemctl daemon-reload
sudo systemctl enable carlbox-sampler
sudo systemctl start carlbox-sampler
```

The service starts both the web interface and MIDI sampler automatically on every boot.

### Service management

```bash
sudo systemctl status carlbox-sampler    # check status
sudo journalctl -u carlbox-sampler -f    # follow live logs
sudo systemctl restart carlbox-sampler   # restart
sudo systemctl stop carlbox-sampler      # stop
sudo systemctl disable carlbox-sampler   # disable auto-start
```

### 11. Updating

To pull the latest code and restart:

```bash
cd /usr/src/carlbox-sampler
sudo git pull
sudo systemctl restart carlbox-sampler
```

If the service file changed, reload systemd:

```bash
sudo systemctl daemon-reload
sudo systemctl restart carlbox-sampler
```

## OLED Display

The 0.96" dual-color OLED (yellow top 16px, blue bottom 48px) shows:

**During startup:**
- Yellow: "CarlBox v2"
- Blue: progress bar with step labels (Init audio, Init MIDI, Loading 3/5...)

**During operation:**
- Yellow: "CarlBox v2"
- Blue: IP address (or "No IP address !"), current status (Ready / Playing KeyX)

### OLED CLI options

```bash
python midi_sampler.py --i2c-bus 2 --i2c-addr 0x3C   # specify bus/address (defaults)
python midi_sampler.py --no-oled                       # disable OLED
```

## Amplifier GPIO Control

The PAM8302A amplifier is controlled via GPIO PC9 (pin 73). The SD (shutdown) pin is held LOW during audio initialization to prevent speaker pops, then set HIGH once the audio subsystem is ready.

```bash
python midi_sampler.py --amp-pin 73    # specify GPIO pin (default)
python midi_sampler.py --no-amp        # disable amplifier control
```

## Web Interface

The web UI runs on port 80, started by `run.py` alongside the MIDI sampler. It allows uploading and deleting audio samples from any browser on the same network.

Open `http://<orangepi-ip>` in a browser, select a key slot and upload a `.wav` or `.mp3` file. The sampler detects new files automatically every 2 seconds.

## MIDI Key Mapping

| Folder | MIDI Note | Function |
|--------|-----------|----------|
| `Key1` | 50 | **STOP** |
| `Key2` | 51 | Play |
| `Key3` | 52 | Play |
| `Key4` | 53 | Play |
| `Key5` | 54 | Play |
| `Key6` | 55 | Play |
| `Key7` | 56 | Play |
| `Key8` | 57 | Play |
| `Key9` | 58 | Play |
| `Key10` | 59 | Play |
| `Key11` | 60 | Play |
| `Key12` | 61 | Play |

## Project Structure

```
carlbox-sampler/
├── midi_sampler.py            # Main MIDI sampler with OLED + amp control
├── reset_midi.py              # MIDI device reset utility
├── run.py                     # Unified launcher (web server + sampler)
├── carlbox-sampler.service    # systemd service (runs run.py)
├── .gitignore
├── README.md
├── docs/plans/                # Design documents
└── piano-upload/
    ├── server.js              # Node.js web upload server (port 80)
    ├── package.json           # Node.js dependencies (express, multer)
    ├── public/                # Web interface static files
    └── uploads/               # Sample storage
        ├── Key1/              # STOP key (no audio file needed)
        ├── Key2/              # Audio files for MIDI note 51
        └── ...
```

## Troubleshooting

### MIDI device not found

1. Check the device is connected: `aconnect -l`
2. Close any other app using MIDI
3. Run: `sudo venv/bin/python reset_midi.py`
4. Unplug and replug the MIDI controller

### OLED display not detected

1. Verify I2C overlay is enabled: `cat /boot/armbianEnv.txt | grep overlays`
   - Should contain `i2c3-ph`
2. Check the display is visible: `sudo i2cdetect -y 2`
   - Should show `3c` in the grid
3. Check wiring (SDA/SCL not swapped, VCC is 3.3V)

### No audio output

1. Check sound card: `aplay -l`
2. Test audio: `aplay -D hw:0,0 /usr/share/sounds/alsa/Front_Center.wav`
3. Check amplifier wiring and GPIO: `cat /sys/class/gpio/gpio73/value` (should be `1` when running)

### Web interface not accessible

1. Check the service is running: `sudo systemctl status carlbox-sampler`
2. Check logs: `sudo journalctl -u carlbox-sampler -n 20`
3. Verify Node.js dependencies: `ls /usr/src/carlbox-sampler/piano-upload/node_modules/`
   - If missing: `cd /usr/src/carlbox-sampler/piano-upload && sudo npm install`
4. Verify port 80 is not used by another service: `sudo ss -tlnp | grep :80`

### Service won't start

```bash
sudo journalctl -u carlbox-sampler -n 50
sudo systemctl status carlbox-sampler
```

---

Built for live performances and jingle playback.
