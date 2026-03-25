# Sonic Halo Debug Tools

This directory contains debugging scripts to help diagnose audio issues, especially on Linux/Steam Deck.

## Scripts

### `audio_device_debug.py`
Comprehensive diagnostic script that:
- Lists all available audio devices
- Checks for PulseAudio/Pipewire monitor sources
- Tests audio capture from devices
- Shows current Sonic Halo settings
- Provides platform-specific recommendations

**Usage:**
```bash
python src/debug/audio_device_debug.py
```

**On Steam Deck:**
```bash
# From Desktop Mode
cd ~/path/to/audio_vis
source .venv/bin/activate  # or use your venv
python src/debug/audio_device_debug.py
```

### `quick_audio_test.py`
Quick audio level meter to verify audio is being captured in real-time.

**Usage:**
```bash
python src/debug/quick_audio_test.py [device_number]
```

## Common Issues on Steam Deck

### No Audio Reaction

**Symptoms:** Window opens but bars don't move

**Solutions:**
1. Run `audio_device_debug.py` to identify available devices
2. Look for devices ending in `.monitor` - these capture system audio
3. Play some music while running the debug script
4. Note the device number that shows audio activity
5. Set `USER_AUDIO_DEVICE` in settings.json to that device number

### Monitor Devices Not Found

**Symptoms:** No `.monitor` devices in device list

**Solutions:**
```bash
# Create a virtual sink that can be monitored
pactl load-module module-null-sink sink_name=visualizer_sink

# This creates visualizer_sink.monitor which Sonic Halo can use
# Then set this as your audio output in system settings
```

### Audio Plays But Still No Bars

**Symptoms:** Audio plays through speakers but visualizer doesn't react

**Cause:** Visualizer is listening to wrong device (e.g., microphone instead of monitor)

**Solution:**
1. Find the correct monitor device with `pactl list short sources`
2. Look for the one matching your active audio output
3. Update `USER_AUDIO_DEVICE` in settings

## Settings File Location

**Linux/Steam Deck:**
```
~/.local/share/Sonic Halo/settings.json
```

**Windows:**
```
C:\Users\<username>\AppData\Local\Dacus\Sonic Halo\settings.json
```

**macOS:**
```
~/Library/Application Support/Sonic Halo/settings.json
```

## Editing Settings

Add or modify these in `settings.json`:

```json
{
  "USER_AUDIO_DEVICE": 5,
  "USE_SYSTEM_AUDIO": false,
  "SAMPLE_RATE": 44100
}
```

- `USER_AUDIO_DEVICE`: Force a specific device (use number from debug script)
- `USE_SYSTEM_AUDIO`: `true` for Windows WASAPI, `false` for regular sounddevice
- `SAMPLE_RATE`: Match your system audio sample rate (usually 44100 or 48000)

## Steam Deck Specific Tips

1. **Desktop Mode:** Easier to debug from Desktop Mode terminal
2. **Pipewire:** Steam Deck uses Pipewire, not pure PulseAudio (but pactl still works)
3. **Default Output:** Make sure you know which output is active (speakers vs HDMI vs headphones)
4. **Monitor Source:** Each output has its own monitor - find the right one
5. **Gaming Mode:** When working correctly in Desktop Mode, it should also work in Gaming Mode

## Getting Help

If issues persist:
1. Run `audio_device_debug.py` and save the output
2. Check what device number shows audio activity
3. Verify that device in Sonic Halo settings
4. Make sure audio is actively playing during tests
