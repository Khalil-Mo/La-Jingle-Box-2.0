"""
MIDI Device Reset Utility

Run this script to reset the MIDI subsystem and release any locked devices.
Use this if the main midi_sampler.py says the device is locked.

Usage: python reset_midi.py
"""

import sys
import time

try:
    import pygame
    import pygame.midi
except ImportError:
    print("Error: pygame is required. Install with: pip install pygame")
    sys.exit(1)

def main():
    print("=" * 50)
    print("      MIDI Device Reset Utility")
    print("=" * 50)
    
    # Step 1: Initialize and list devices
    print("\n1. Initializing pygame.midi...")
    pygame.midi.init()
    
    print("\n2. Scanning MIDI devices...")
    device_count = pygame.midi.get_count()
    print(f"   Found {device_count} MIDI devices:\n")
    
    input_devices = []
    for i in range(device_count):
        info = pygame.midi.get_device_info(i)
        name = info[1].decode('utf-8') if isinstance(info[1], bytes) else info[1]
        is_input = info[2]
        is_opened = info[4]
        device_type = "INPUT" if is_input else "OUTPUT"
        status = "LOCKED/OPEN" if is_opened else "available"
        print(f"   [{i}] {name} ({device_type}) - {status}")
        
        if is_input:
            input_devices.append((i, name, is_opened))
    
    # Step 2: Check for locked devices
    locked_devices = [d for d in input_devices if d[2]]
    
    if locked_devices:
        print(f"\n3. WARNING: Found {len(locked_devices)} locked INPUT device(s)!")
        for dev_id, name, _ in locked_devices:
            print(f"   - [{dev_id}] {name}")
        print("\n   These devices are in use by another process.")
    else:
        print("\n3. No locked devices detected.")
    
    # Step 3: Attempt reset cycle
    print("\n4. Performing reset cycle...")
    
    # Multiple quit/init cycles
    for i in range(3):
        print(f"   Reset cycle {i+1}/3...")
        pygame.midi.quit()
        time.sleep(0.5)
        pygame.midi.init()
        time.sleep(0.2)
    
    print("\n5. Re-scanning after reset...")
    device_count = pygame.midi.get_count()
    
    still_locked = False
    for i in range(device_count):
        info = pygame.midi.get_device_info(i)
        name = info[1].decode('utf-8') if isinstance(info[1], bytes) else info[1]
        is_input = info[2]
        is_opened = info[4]
        if is_input:
            status = "STILL LOCKED" if is_opened else "AVAILABLE"
            if is_opened:
                still_locked = True
            print(f"   [{i}] {name} - {status}")
    
    # Final cleanup
    pygame.midi.quit()
    
    print("\n" + "=" * 50)
    if still_locked:
        print("Some devices are still locked!")
        print("\nTo fix this:")
        print("1. Close ALL other applications that might use MIDI")
        print("   (DAWs, MIDI monitors, other Python scripts, etc.)")
        print("2. Unplug and replug your MIDI device")
        print("3. If still not working, restart your computer")
    else:
        print("Reset complete! MIDI devices should now be available.")
        print("Try running midi_sampler.py again.")
    print("=" * 50)


if __name__ == '__main__':
    main()
