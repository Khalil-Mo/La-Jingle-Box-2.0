#!/usr/bin/env python3
"""
CarlBox Server — BLE GATT Peripheral + MIDI Sampler

Single-process server that:
- Exposes a BLE GATT service for sample management (upload, list, delete)
- Runs the MIDI sampler for audio playback

Both subsystems share one asyncio event loop.
"""

import os
import sys
import json
import signal
import asyncio
import logging

# Force unbuffered output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)

from bless import BlessServer, BlessGATTCharacteristic, GATTCharacteristicProperties, GATTAttributePermissions

# Import MIDI sampler components
from midi_sampler import (
    SampleLoader,
    NOTE_MAPPING,
    NOTE_TO_KEY,
    initialize_audio,
    initialize_midi,
    cleanup_resources,
    handle_midi_message,
    setup_signal_handlers,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- BLE Constants ---
SERVICE_UUID = "CB000001-CB00-CB00-CB00-CB0000000000"
FILE_LIST_UUID = "CB000002-CB00-CB00-CB00-CB0000000000"
FILE_TRANSFER_UUID = "CB000003-CB00-CB00-CB00-CB0000000000"
FILE_COMMAND_UUID = "CB000004-CB00-CB00-CB00-CB0000000000"
TRANSFER_STATUS_UUID = "CB000005-CB00-CB00-CB00-CB0000000000"

CHUNK_SIZE = 512
SUPPORTED_EXTENSIONS = ('.wav', '.mp3')


# --- File Manager ---

class FileManager:
    """Manages sample files on disk (list, delete, upload via chunked transfer)."""

    def __init__(self, uploads_dir: str):
        self.uploads_dir = uploads_dir
        os.makedirs(uploads_dir, exist_ok=True)

        # Upload state
        self._upload_key = None
        self._upload_filename = None
        self._upload_expected_size = 0
        self._upload_buffer = bytearray()

    def list_all_files(self) -> dict:
        """List all samples grouped by key. Returns {Key1: [...], Key2: [...], ...}."""
        result = {}
        for key_name in NOTE_MAPPING:
            key_dir = os.path.join(self.uploads_dir, key_name)
            files = []
            if os.path.isdir(key_dir):
                try:
                    files = sorted(
                        f for f in os.listdir(key_dir)
                        if f.lower().endswith(SUPPORTED_EXTENSIONS) and not f.startswith('.')
                    )
                except OSError:
                    pass
            result[key_name] = files
        return result

    def list_files(self, key: str) -> list:
        """List sample files for a single key."""
        return self.list_all_files().get(key, [])

    def delete_file(self, key: str, filename: str) -> bool:
        """Delete a sample file. Returns True on success."""
        # Sanitize: prevent path traversal
        safe_filename = os.path.basename(filename)
        file_path = os.path.join(self.uploads_dir, key, safe_filename)
        try:
            if os.path.isfile(file_path):
                os.remove(file_path)
                logger.info(f"[FILE] Deleted {key}/{safe_filename}")
                return True
            else:
                logger.warning(f"[FILE] Not found: {key}/{safe_filename}")
                return False
        except OSError as e:
            logger.error(f"[FILE] Delete error: {e}")
            return False

    def begin_upload(self, key: str, filename: str, size: int):
        """Prepare for an incoming chunked file transfer."""
        self._upload_key = key
        self._upload_filename = os.path.basename(filename)
        self._upload_expected_size = size
        self._upload_buffer = bytearray()
        logger.info(f"[UPLOAD] Starting: {key}/{self._upload_filename} ({size} bytes)")

    def receive_chunk(self, data: bytes) -> int:
        """Append a chunk to the upload buffer. Returns total bytes received."""
        self._upload_buffer.extend(data)
        return len(self._upload_buffer)

    @property
    def upload_in_progress(self) -> bool:
        return self._upload_key is not None

    @property
    def upload_complete(self) -> bool:
        return (
            self._upload_key is not None
            and len(self._upload_buffer) >= self._upload_expected_size
        )

    @property
    def bytes_received(self) -> int:
        return len(self._upload_buffer)

    def finalize_upload(self) -> bool:
        """Write the accumulated buffer to disk. Returns True on success."""
        if not self._upload_key or not self._upload_filename:
            return False

        key_dir = os.path.join(self.uploads_dir, self._upload_key)
        os.makedirs(key_dir, exist_ok=True)
        file_path = os.path.join(key_dir, self._upload_filename)

        try:
            with open(file_path, 'wb') as f:
                f.write(self._upload_buffer)
            logger.info(
                f"[UPLOAD] Complete: {self._upload_key}/{self._upload_filename} "
                f"({len(self._upload_buffer)} bytes)"
            )
            return True
        except OSError as e:
            logger.error(f"[UPLOAD] Write error: {e}")
            return False
        finally:
            self._reset_upload()

    def _reset_upload(self):
        self._upload_key = None
        self._upload_filename = None
        self._upload_expected_size = 0
        self._upload_buffer = bytearray()

    def get_transfer_status(self) -> dict:
        """Return current transfer state as a dict."""
        if not self.upload_in_progress:
            return {"status": "idle"}
        return {
            "status": "receiving",
            "key": self._upload_key,
            "filename": self._upload_filename,
            "bytes_received": self.bytes_received,
            "bytes_expected": self._upload_expected_size,
        }


# --- BLE Server Setup ---

def get_uploads_dir() -> str:
    """Resolve the uploads directory path."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, "uploads")


def _json_bytes(obj) -> bytearray:
    """Encode a Python object as JSON bytes (bytearray for bless)."""
    return bytearray(json.dumps(obj, separators=(',', ':')).encode('utf-8'))


def _notify_characteristic(server: BlessServer, uuid: str, data: bytearray):
    """Update a characteristic value and send a notification."""
    server.get_characteristic(uuid).value = data
    server.update_value(SERVICE_UUID, uuid)


class BLEHandler:
    """Handles BLE read/write callbacks for the GATT characteristics."""

    def __init__(self, file_manager: FileManager, server: BlessServer):
        self.fm = file_manager
        self.server = server

    def on_read(self, characteristic: BlessGATTCharacteristic, **kwargs) -> bytearray:
        uuid = characteristic.uuid.upper()

        if uuid == FILE_LIST_UUID.upper():
            return _json_bytes(self.fm.list_all_files())

        if uuid == TRANSFER_STATUS_UUID.upper():
            return _json_bytes(self.fm.get_transfer_status())

        return bytearray(b'')

    def on_write(self, characteristic: BlessGATTCharacteristic, value: bytearray, **kwargs):
        uuid = characteristic.uuid.upper()

        if uuid == FILE_COMMAND_UUID.upper():
            self._handle_command(value)

        elif uuid == FILE_TRANSFER_UUID.upper():
            self._handle_transfer_chunk(value)

    def _handle_command(self, value: bytearray):
        """Parse and dispatch a JSON command."""
        try:
            cmd = json.loads(value.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"[BLE] Bad command payload: {e}")
            self._notify_status({"status": "error", "message": "invalid JSON"})
            return

        action = cmd.get("action")

        if action == "upload":
            key = cmd.get("key", "")
            filename = cmd.get("filename", "")
            size = cmd.get("size", 0)
            if not key or not filename or size <= 0:
                self._notify_status({"status": "error", "message": "missing key/filename/size"})
                return
            self.fm.begin_upload(key, filename, size)
            self._notify_status({"status": "ready"})

        elif action == "delete":
            key = cmd.get("key", "")
            filename = cmd.get("filename", "")
            if not key or not filename:
                self._notify_status({"status": "error", "message": "missing key/filename"})
                return
            success = self.fm.delete_file(key, filename)
            self._notify_status({"status": "deleted" if success else "error"})
            # Notify updated file list
            self._notify_file_list()

        else:
            logger.warning(f"[BLE] Unknown action: {action}")
            self._notify_status({"status": "error", "message": f"unknown action: {action}"})

    def _handle_transfer_chunk(self, value: bytearray):
        """Handle an incoming raw data chunk for file upload."""
        if not self.fm.upload_in_progress:
            logger.warning("[BLE] Received chunk but no upload in progress")
            return

        total = self.fm.receive_chunk(bytes(value))

        if self.fm.upload_complete:
            success = self.fm.finalize_upload()
            self._notify_status({"status": "complete" if success else "error"})
            self._notify_file_list()
        else:
            # Periodic progress (every ~10 chunks to avoid flooding)
            if total % (CHUNK_SIZE * 10) < CHUNK_SIZE:
                self._notify_status(self.fm.get_transfer_status())

    def _notify_status(self, status: dict):
        _notify_characteristic(self.server, TRANSFER_STATUS_UUID, _json_bytes(status))

    def _notify_file_list(self):
        _notify_characteristic(self.server, FILE_LIST_UUID, _json_bytes(self.fm.list_all_files()))


async def start_ble_server(file_manager: FileManager) -> BlessServer:
    """Create, configure, and start the BLE GATT server."""

    # Trigger used to wait until server is ready
    trigger = asyncio.Event()

    def on_client_connect(client_id):
        logger.info(f"[BLE] Client connected: {client_id}")

    def on_client_disconnect(client_id):
        logger.info(f"[BLE] Client disconnected: {client_id}")

    server = BlessServer(name="CarlBox", loop=asyncio.get_event_loop())
    server.read_request_func = None   # Set after handler creation
    server.write_request_func = None

    handler = BLEHandler(file_manager, server)

    server.read_request_func = handler.on_read
    server.write_request_func = handler.on_write

    await server.add_new_service(SERVICE_UUID)

    # File List — Read + Notify
    char_flags = (
        GATTCharacteristicProperties.read
        | GATTCharacteristicProperties.notify
    )
    permissions = GATTAttributePermissions.readable
    await server.add_new_characteristic(
        SERVICE_UUID, FILE_LIST_UUID, char_flags, _json_bytes({}), permissions
    )

    # File Transfer — Write Without Response
    char_flags = GATTCharacteristicProperties.write_without_response
    permissions = GATTAttributePermissions.writeable
    await server.add_new_characteristic(
        SERVICE_UUID, FILE_TRANSFER_UUID, char_flags, bytearray(b''), permissions
    )

    # File Command — Write
    char_flags = GATTCharacteristicProperties.write
    permissions = GATTAttributePermissions.writeable
    await server.add_new_characteristic(
        SERVICE_UUID, FILE_COMMAND_UUID, char_flags, bytearray(b''), permissions
    )

    # Transfer Status — Read + Notify
    char_flags = (
        GATTCharacteristicProperties.read
        | GATTCharacteristicProperties.notify
    )
    permissions = GATTAttributePermissions.readable
    await server.add_new_characteristic(
        SERVICE_UUID, TRANSFER_STATUS_UUID, char_flags,
        _json_bytes({"status": "idle"}), permissions
    )

    await server.start()
    logger.info("[BLE] GATT server started — advertising as 'CarlBox'")

    return server


# --- MIDI Loop ---

async def midi_loop(midi_port, loader: SampleLoader):
    """Async loop that polls MIDI input and checks for sample file changes."""
    logger.info("[MIDI] Sampler loop running")
    while True:
        try:
            msg = midi_port.poll()
            if msg:
                handle_midi_message(msg, loader)
            loader.scan_and_update()
        except Exception as e:
            logger.error(f"[MIDI] Loop error: {e}")
            await asyncio.sleep(0.1)
            continue
        await asyncio.sleep(0.001)


# --- Main ---

async def main():
    import midi_sampler  # for global midi_port reference

    print("=" * 50)
    print("       CARLBOX SERVER")
    print("       BLE + MIDI Sampler")
    print("=" * 50)

    # 1. Initialize audio
    if not initialize_audio():
        print("[ERROR] Failed to initialize audio!")
        cleanup_resources()
        sys.exit(1)

    # 2. Initialize MIDI
    midi_port = initialize_midi()
    if midi_port is None:
        print()
        print("=" * 50)
        print("[ERROR] No MIDI device available!")
        print("=" * 50)
        print()
        print("Troubleshooting:")
        print("1. Make sure MIDI controller is connected")
        print("2. Close other apps using MIDI (DAWs, etc.)")
        print("3. Run: python reset_midi.py")
        print("4. Unplug/replug MIDI device")
        cleanup_resources()
        sys.exit(1)

    # Keep reference for cleanup
    midi_sampler.midi_port = midi_port

    # 3. Setup sample loader
    uploads_dir = get_uploads_dir()
    os.makedirs(uploads_dir, exist_ok=True)
    loader = SampleLoader(uploads_dir)
    loader.scan_and_update()

    if not loader.samples:
        print("[WARN] No samples loaded initially")

    # 4. Setup file manager + BLE server
    file_manager = FileManager(uploads_dir)
    ble_server = await start_ble_server(file_manager)

    # 5. Report ready
    print()
    print("=" * 50)
    print("*** READY ***")
    print("=" * 50)
    print(f"MIDI device : {getattr(midi_port, 'name', 'Unknown')}")
    print(f"Uploads dir : {uploads_dir}")
    print(f"BLE service : {SERVICE_UUID}")
    print("Hot-reload  : checking for new files every 2s")
    print("Press Ctrl+C to quit.")
    print()

    # 6. Run BLE server + MIDI loop concurrently
    try:
        await midi_loop(midi_port, loader)
    except asyncio.CancelledError:
        pass
    finally:
        logger.info("[SHUTDOWN] Stopping BLE server...")
        await ble_server.stop()
        cleanup_resources()
        logger.info("[SHUTDOWN] Complete")


def _shutdown(loop: asyncio.AbstractEventLoop):
    """Cancel all running tasks for a clean shutdown."""
    for task in asyncio.all_tasks(loop):
        task.cancel()


if __name__ == '__main__':
    loop = asyncio.new_event_loop()

    # Wire Ctrl+C to cancel the event loop tasks
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown, loop)

    try:
        loop.run_until_complete(main())
    except asyncio.CancelledError:
        pass
    finally:
        loop.close()
