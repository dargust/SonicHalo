#!/usr/bin/env python3
"""
Quick Audio Level Test for Sonic Halo
Real-time audio level meter to verify device is capturing audio
"""

import sys
import numpy as np
import sounddevice as sd
import time

def audio_level_meter(device=None, duration=10):
    """
    Display real-time audio levels from specified device
    
    Args:
        device: Device index or None for default
        duration: How long to run the test (seconds)
    """
    print("=" * 70)
    print("Sonic Halo - Quick Audio Level Test")
    print("=" * 70)
    
    # Get device info
    if device is not None:
        try:
            device_info = sd.query_devices(device)
            print(f"Testing device {device}: {device_info['name']}")
        except:
            print(f"Error: Device {device} not found")
            print("\nAvailable devices:")
            devices = sd.query_devices()
            for i, dev in enumerate(devices):
                if dev['max_input_channels'] > 0:
                    print(f"  {i}: {dev['name']}")
            return
    else:
        device_info = sd.query_devices(sd.default.device[0])
        print(f"Testing default input: {device_info['name']}")
    
    print(f"Sample rate: {device_info['default_samplerate']} Hz")
    print(f"Channels: {device_info['max_input_channels']}")
    print("\n" + "=" * 70)
    print("Audio Level Meter (press Ctrl+C to stop)")
    print("=" * 70)
    print("\nMake sure audio is playing!\n")
    
    # Setup stream
    audio_data = []
    
    def callback(indata, frames, time_info, status):
        if status:
            print(f"Status: {status}")
        audio_data.append(indata.copy())
    
    try:
        stream = sd.InputStream(
            device=device,
            channels=min(2, device_info['max_input_channels']),
            samplerate=int(device_info['default_samplerate']),
            blocksize=2048,
            callback=callback
        )
        
        stream.start()
        start_time = time.time()
        peak_seen = 0.0
        
        while time.time() - start_time < duration:
            time.sleep(0.1)
            
            if audio_data:
                # Get recent data
                recent_data = np.concatenate(audio_data[-5:]) if len(audio_data) >= 5 else np.concatenate(audio_data)
                audio_data.clear()
                
                # Calculate levels
                max_amp = np.max(np.abs(recent_data))
                mean_amp = np.mean(np.abs(recent_data))
                rms = np.sqrt(np.mean(recent_data**2))
                
                peak_seen = max(peak_seen, max_amp)
                
                # Create visual bar
                bar_length = 50
                level_bar = int(max_amp * bar_length * 10)  # Scale for visibility
                bar = "█" * min(level_bar, bar_length)
                
                # Print level with status
                status_msg = ""
                if max_amp > 0.01:
                    status_msg = "✓ AUDIO DETECTED!"
                elif max_amp > 0.001:
                    status_msg = "~ Weak signal"
                else:
                    status_msg = "✗ No audio"
                
                print(f"\rLevel: {bar:<50} | Max: {max_amp:.6f} | {status_msg}", end="", flush=True)
        
        stream.stop()
        stream.close()
        
        print("\n\n" + "=" * 70)
        print("Test Complete")
        print("=" * 70)
        print(f"Duration: {duration} seconds")
        print(f"Peak amplitude seen: {peak_seen:.6f}")
        
        if peak_seen > 0.01:
            print("\n✓✓✓ SUCCESS! Audio is being captured properly!")
            print(f"\nThis device ({device if device is not None else 'default'}) should work with Sonic Halo.")
            if device is not None:
                print(f"\nAdd this to your settings.json:")
                print(f'  "USER_AUDIO_DEVICE": {device}')
        elif peak_seen > 0.0001:
            print("\n⚠ WARNING: Audio signal is very weak!")
            print("  - Make sure audio is actually playing")
            print("  - Check system volume level")
            print("  - This might work but may not be very responsive")
        else:
            print("\n✗ FAILED: No audio captured!")
            print("  - Make sure audio is playing during the test")
            print("  - Try a different device")
            print("  - This device may not be suitable for audio capture")
        
    except KeyboardInterrupt:
        print("\n\nTest stopped by user")
        stream.stop()
        stream.close()
    except Exception as e:
        print(f"\n\nError during capture: {e}")

def main():
    print("\nQuick Audio Level Test for Sonic Halo\n")
    
    if len(sys.argv) > 1:
        try:
            device = int(sys.argv[1])
            duration = int(sys.argv[2]) if len(sys.argv) > 2 else 10
            audio_level_meter(device, duration)
        except ValueError:
            print("Usage: python quick_audio_test.py [device_number] [duration_seconds]")
            print("\nExample: python quick_audio_test.py 5 10")
    else:
        # Interactive mode
        print("Available input devices:")
        devices = sd.query_devices()
        input_devices = []
        
        for i, dev in enumerate(devices):
            if dev['max_input_channels'] > 0:
                input_devices.append(i)
                is_default = " [DEFAULT]" if i == sd.default.device[0] else ""
                is_monitor = " [MONITOR]" if 'monitor' in dev['name'].lower() else ""
                print(f"  {i}: {dev['name']}{is_default}{is_monitor}")
        
        print("\nEnter device number to test (or press Enter for default):")
        choice = input("> ").strip()
        
        if choice:
            try:
                device = int(choice)
                if device not in input_devices:
                    print(f"Device {device} has no input channels!")
                    return
            except ValueError:
                print("Invalid device number")
                return
        else:
            device = None
        
        print("\nTest duration in seconds (default: 10):")
        duration_input = input("> ").strip()
        duration = int(duration_input) if duration_input else 10
        
        print(f"\nStarting {duration} second test...")
        time.sleep(1)
        audio_level_meter(device, duration)

if __name__ == "__main__":
    main()
