#!/usr/bin/env python3
"""
Audio Device Debug Script for Sonic Halo
Helps diagnose audio device issues, especially on Linux/Steam Deck
"""

import sys
import os
import logging
import subprocess
import platform

# Setup logging
logging.basicConfig(level=logging.INFO, format='{levelname} - {message}', style='{')

print("=" * 70)
print("Sonic Halo Audio Device Debug Script")
print("=" * 70)
print(f"Platform: {platform.system()} {platform.release()}")
print(f"Python: {sys.version}")
print("=" * 70)

ON_LINUX = sys.platform.startswith('linux')
ON_MACOS = sys.platform.startswith('darwin')
ON_WINDOWS = sys.platform.startswith('win')

# ============================================================================
# 1. Test SoundDevice Library
# ============================================================================
print("\n[1] Testing sounddevice library...")
try:
    import sounddevice as sd
    print("✓ sounddevice imported successfully")
    print(f"  Version: {sd.__version__}")
    print(f"  Default input device: {sd.default.device[0]}")
    print(f"  Default output device: {sd.default.device[1]}")
    print(f"  Default samplerate: {sd.default.samplerate}")
except ImportError as e:
    print(f"✗ Failed to import sounddevice: {e}")
    print("  Install with: pip install sounddevice")
    sys.exit(1)

# ============================================================================
# 2. List All Audio Devices
# ============================================================================
print("\n[2] Available Audio Devices:")
print("-" * 70)
try:
    devices = sd.query_devices()
    print(f"Total devices found: {len(devices)}\n")
    
    for i, dev in enumerate(devices):
        is_default_in = (i == sd.default.device[0])
        is_default_out = (i == sd.default.device[1])
        default_marker = ""
        if is_default_in:
            default_marker += " [DEFAULT INPUT]"
        if is_default_out:
            default_marker += " [DEFAULT OUTPUT]"
        
        print(f"Device {i}: {dev['name']}{default_marker}")
        print(f"  Max Input Channels:  {dev['max_input_channels']}")
        print(f"  Max Output Channels: {dev['max_output_channels']}")
        print(f"  Default Sample Rate: {dev['default_samplerate']} Hz")
        
        # Highlight potential system audio capture devices
        dev_name_lower = dev['name'].lower()
        if dev['max_input_channels'] > 0:
            if ON_LINUX and ('monitor' in dev_name_lower or dev['name'].endswith('.monitor')):
                print(f"  >>> LINUX SYSTEM AUDIO MONITOR DETECTED <<<")
            elif ON_MACOS and ('blackhole' in dev_name_lower or 'soundflower' in dev_name_lower):
                print(f"  >>> MACOS VIRTUAL AUDIO DEVICE DETECTED <<<")
            elif ON_WINDOWS and ('stereo mix' in dev_name_lower or 'cable' in dev_name_lower):
                print(f"  >>> WINDOWS VIRTUAL AUDIO DEVICE DETECTED <<<")
        print()
        
except Exception as e:
    print(f"✗ Error querying devices: {e}")

# ============================================================================
# 3. Platform-Specific Audio System Info
# ============================================================================
print("\n[3] Platform-Specific Audio System:")
print("-" * 70)

if ON_LINUX:
    print("Linux audio system detected")
    
    # Check for PulseAudio
    print("\n[3a] Checking PulseAudio/Pipewire sources:")
    try:
        result = subprocess.run(['pactl', 'list', 'short', 'sources'], 
                              capture_output=True, text=True, check=True, timeout=5)
        print("✓ PulseAudio/Pipewire is available\n")
        
        monitor_count = 0
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                parts = line.split('\t')
                if len(parts) >= 2:
                    source_id = parts[0]
                    source_name = parts[1]
                    print(f"  Source {source_id}: {source_name}")
                    
                    if source_name.endswith('.monitor'):
                        monitor_count += 1
                        print(f"    >>> THIS IS A MONITOR SOURCE (SYSTEM AUDIO) <<<")
        
        print(f"\nTotal monitor sources found: {monitor_count}")
        
        if monitor_count == 0:
            print("\n⚠ WARNING: No monitor sources found!")
            print("  Monitor sources capture system audio output.")
            print("  You may need to enable them in your audio settings.")
            
    except subprocess.CalledProcessError as e:
        print(f"✗ Error running pactl: {e}")
        print("  PulseAudio might not be installed or running")
    except FileNotFoundError:
        print("✗ pactl command not found")
        print("  PulseAudio tools not installed")
    except subprocess.TimeoutExpired:
        print("✗ pactl command timed out")
    
    # Check for ALSA
    print("\n[3b] Checking ALSA devices:")
    try:
        result = subprocess.run(['arecord', '-L'], 
                              capture_output=True, text=True, timeout=5)
        if 'Loopback' in result.stdout or 'Monitor' in result.stdout:
            print("✓ ALSA loopback/monitor devices found")
        else:
            print("  No ALSA loopback devices found (this is normal if using PulseAudio)")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("  Could not query ALSA devices")
    except subprocess.TimeoutExpired:
        print("✗ arecord command timed out")
    
    # Steam Deck specific check
    print("\n[3c] Steam Deck specific checks:")
    if os.path.exists('/home/deck'):
        print("✓ Steam Deck user detected")
        print("  Your device uses Pipewire with PulseAudio compatibility")
        print("  Monitor sources should be available for system audio capture")
    else:
        print("  Not running on Steam Deck (or not as 'deck' user)")

elif ON_MACOS:
    print("macOS detected")
    print("\nFor system audio capture on macOS, you need:")
    print("  - BlackHole: https://github.com/ExistentialAudio/BlackHole")
    print("  - or Soundflower: https://github.com/mattingalls/Soundflower")
    print("\nCheck if any virtual devices were detected above.")

elif ON_WINDOWS:
    print("Windows detected")
    print("\nFor system audio capture on Windows, you need:")
    print("  - Stereo Mix (built-in, enable in Recording Devices)")
    print("  - or VB-Audio Virtual Cable: https://vb-audio.com/Cable/")
    print("  - or WASAPI Loopback (supported by this app)")

# ============================================================================
# 4. Test Audio Capture
# ============================================================================
print("\n[4] Testing Audio Capture:")
print("-" * 70)

def test_device_capture(device_id, duration_sec=2, display_samples=10):
    """Test capturing audio from a device"""
    import numpy as np
    import time
    
    try:
        print(f"  Testing device {device_id}...")
        captured_data = []
        
        def callback(indata, frames, time_info, status):
            if status:
                print(f"  Status: {status}")
            captured_data.append(indata.copy())
        
        stream = sd.InputStream(
            device=device_id,
            channels=2,
            samplerate=44100,
            blocksize=2048,
            callback=callback
        )
        
        stream.start()
        print(f"  Recording for {duration_sec} seconds...")
        time.sleep(duration_sec)
        stream.stop()
        stream.close()
        
        if captured_data:
            all_data = np.concatenate(captured_data)
            max_amplitude = np.max(np.abs(all_data))
            mean_amplitude = np.mean(np.abs(all_data))
            
            print(f"  ✓ Capture successful!")
            print(f"    Captured {len(all_data)} samples")
            print(f"    Max amplitude: {max_amplitude:.6f}")
            print(f"    Mean amplitude: {mean_amplitude:.6f}")
            
            # Show first few samples
            print(f"    First {display_samples} samples: {all_data[:display_samples].flatten()[:display_samples]}")
            
            if max_amplitude < 0.0001:
                print(f"  ⚠ WARNING: Audio signal is very weak or silent!")
                print(f"    Make sure audio is playing during the test.")
                return False
            else:
                print(f"  ✓ Audio signal detected!")
                return True
        else:
            print(f"  ✗ No data captured")
            return False
            
    except Exception as e:
        print(f"  ✗ Error capturing from device {device_id}: {e}")
        return False

# Test devices with input channels
print("\nSelect a device to test (or press Enter to test all monitor devices):")
test_choice = input("Device number: ").strip()

if test_choice:
    try:
        device_num = int(test_choice)
        test_device_capture(device_num)
    except ValueError:
        print("Invalid device number")
else:
    # Auto-test all monitor/virtual devices
    print("\nAuto-testing potential system audio devices...")
    devices = sd.query_devices()
    tested_any = False
    
    for i, dev in enumerate(devices):
        if dev['max_input_channels'] > 0:
            dev_name_lower = dev['name'].lower()
            should_test = False
            
            if ON_LINUX and ('monitor' in dev_name_lower or dev['name'].endswith('.monitor')):
                should_test = True
            elif ON_MACOS and ('blackhole' in dev_name_lower or 'soundflower' in dev_name_lower):
                should_test = True
            elif ON_WINDOWS and ('stereo mix' in dev_name_lower or 'cable' in dev_name_lower):
                should_test = True
            
            if should_test:
                print(f"\nTesting Device {i}: {dev['name']}")
                if test_device_capture(i):
                    print(f"\n✓✓✓ Device {i} appears to be working! ✓✓✓")
                    print(f"Use this device index in your settings: {i}")
                tested_any = True
    
    if not tested_any:
        print("\nNo system audio devices found to test.")
        print("You may need to set up virtual audio devices for system audio capture.")

# ============================================================================
# 5. Check Sonic Halo Settings
# ============================================================================
print("\n[5] Checking Sonic Halo Settings:")
print("-" * 70)

try:
    import platformdirs
    settings_dir = platformdirs.user_data_dir("Sonic Halo", "Dacus")
    settings_file = os.path.join(settings_dir, "settings.json")
    
    print(f"Settings directory: {settings_dir}")
    
    if os.path.exists(settings_file):
        print(f"✓ Settings file found: {settings_file}")
        
        import json
        with open(settings_file, 'r') as f:
            settings = json.load(f)
        
        print(f"\nCurrent audio settings:")
        print(f"  USE_SYSTEM_AUDIO: {settings.get('USE_SYSTEM_AUDIO', 'not set')}")
        print(f"  USER_AUDIO_DEVICE: {settings.get('USER_AUDIO_DEVICE', 'not set')}")
        print(f"  INCLUDE_MIC_INPUT: {settings.get('INCLUDE_MIC_INPUT', 'not set')}")
        print(f"  MIC_DEVICE: {settings.get('MIC_DEVICE', 'not set')}")
        print(f"  SAMPLE_RATE: {settings.get('SAMPLE_RATE', 'not set')}")
        
        # Suggest changes if needed
        user_device = settings.get('USER_AUDIO_DEVICE')
        if user_device is not None:
            print(f"\n✓ Custom device is set: {user_device}")
            try:
                dev = sd.query_devices(user_device)
                print(f"  Device name: {dev['name']}")
                if dev['max_input_channels'] == 0:
                    print(f"  ⚠ WARNING: This device has no input channels!")
            except:
                print(f"  ⚠ WARNING: Device {user_device} not found!")
        else:
            print(f"\n  No custom device set (will auto-detect)")
            
    else:
        print(f"  Settings file not found (using defaults)")
        print(f"  File will be created at: {settings_file}")
        
except Exception as e:
    print(f"✗ Error checking settings: {e}")

# ============================================================================
# 6. Recommendations
# ============================================================================
print("\n[6] Recommendations:")
print("=" * 70)

if ON_LINUX:
    print("For Steam Deck / Linux:")
    print("  1. Ensure audio is actually playing during testing")
    print("  2. Look for devices with '.monitor' suffix above")
    print("  3. If no monitor devices found, run:")
    print("     pactl load-module module-null-sink sink_name=visualizer_sink")
    print("  4. Set USER_AUDIO_DEVICE in settings to the monitor device number")
    print("  5. Try setting USE_SYSTEM_AUDIO to false and using a monitor device")
    
elif ON_MACOS:
    print("For macOS:")
    print("  1. Install BlackHole or Soundflower")
    print("  2. Set it as your audio output in System Preferences")
    print("  3. The app will detect it automatically")
    
elif ON_WINDOWS:
    print("For Windows:")
    print("  1. Enable Stereo Mix in Recording Devices, OR")
    print("  2. Install VB-Audio Virtual Cable")
    print("  3. The app will use WASAPI loopback automatically")

print("\n" + "=" * 70)
print("Debug script complete!")
print("=" * 70)
