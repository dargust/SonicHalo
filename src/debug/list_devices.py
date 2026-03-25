#!/usr/bin/env python3
"""
Simple audio device lister for Sonic Halo
Quick lookup of device numbers and names
"""

import sounddevice as sd

print("Sonic Halo - Audio Device List")
print("=" * 70)

try:
    devices = sd.query_devices()
    
    print(f"\nInput Devices (can capture audio):")
    print("-" * 70)
    for i, dev in enumerate(devices):
        if dev['max_input_channels'] > 0:
            is_default = " ← DEFAULT INPUT" if i == sd.default.device[0] else ""
            is_monitor = " [SYSTEM AUDIO]" if ('monitor' in dev['name'].lower() or 
                                               dev['name'].endswith('.monitor')) else ""
            print(f"{i:3d}: {dev['name']}{is_monitor}{is_default}")
    
    print(f"\nOutput Devices (for reference):")
    print("-" * 70)
    for i, dev in enumerate(devices):
        if dev['max_output_channels'] > 0:
            is_default = " ← DEFAULT OUTPUT" if i == sd.default.device[1] else ""
            print(f"{i:3d}: {dev['name']}{is_default}")
    
    print("\n" + "=" * 70)
    print("To use a device with Sonic Halo:")
    print('  Add to settings.json: "USER_AUDIO_DEVICE": <number>')
    print("\nFor system audio, use a device marked [SYSTEM AUDIO]")
    print("=" * 70)
    
except Exception as e:
    print(f"Error: {e}")
