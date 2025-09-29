# WASAPI loopback capture using PyAudioWPatch (Windows-specific)
import pyaudiowpatch as pyaudio
import numpy as np
import time

def list_loopback_devices():
    """List all available loopback devices"""
    p = pyaudio.PyAudio()
    
    print("Available audio devices:")
    loopback_devices = []
    
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        print(f"Device {i}: {info['name']}")
        print(f"  Max input channels: {info['maxInputChannels']}")
        print(f"  Max output channels: {info['maxOutputChannels']}")
        print(f"  Default sample rate: {info['defaultSampleRate']}")
        
        # Check if this is a WASAPI loopback device
        if info['maxInputChannels'] > 0 and "loopback" in info['name'].lower():
            loopback_devices.append(i)
            print(f"  ✓ LOOPBACK DEVICE FOUND!")
        print()
    
    p.terminate()
    return loopback_devices

def capture_with_wasapi_loopback():
    """Capture system audio using PyAudioWPatch WASAPI loopback"""
    
    # Get the default WASAPI loopback device
    p = pyaudio.PyAudio()
    
    try:
        # Try to get the default WASAPI loopback device
        wasapi_info = p.get_default_wasapi_loopback()
        if wasapi_info:
            print(f"Found default WASAPI loopback device: {wasapi_info['name']}")
            device_id = wasapi_info['index']
        else:
            print("No default WASAPI loopback device found.")
            
            # List all devices and look for loopback devices
            loopback_devices = list_loopback_devices()
            
            if not loopback_devices:
                print("No loopback devices found. Looking for output devices to try...")
                
                # Try to use any output device for loopback
                for i in range(p.get_device_count()):
                    info = p.get_device_info_by_index(i)
                    if (info['maxOutputChannels'] > 0 and 
                        'wasapi' in info['name'].lower() and
                        ('speakers' in info['name'].lower() or 'headphones' in info['name'].lower())):
                        print(f"Trying output device for loopback: {info['name']}")
                        device_id = i
                        break
                else:
                    print("No suitable devices found.")
                    p.terminate()
                    return
            else:
                device_id = loopback_devices[0]
                print(f"Using loopback device {device_id}")
        
        # Get device info
        device_info = p.get_device_info_by_index(device_id)
        sample_rate = int(device_info['defaultSampleRate'])
        channels = device_info['maxInputChannels'] if device_info['maxInputChannels'] > 0 else 2
        
        print(f"Opening stream: {device_info['name']}")
        print(f"Sample rate: {sample_rate}, Channels: {channels}")
        
        # Open input stream
        stream = p.open(format=pyaudio.paInt16,
                       channels=channels,
                       rate=sample_rate,
                       input=True,
                       input_device_index=device_id,
                       frames_per_buffer=1024)
        
        print("Successfully opened WASAPI loopback stream!")
        print("Capturing system audio. Press Ctrl+C to stop.")
        print("Play some audio to see volume levels...")
        
        while True:
            try:
                data = stream.read(1024, exception_on_overflow=False)
                samples = np.frombuffer(data, dtype=np.int16)
                
                # Calculate RMS volume
                rms = np.sqrt(np.mean(samples.astype(np.float32) ** 2))
                if rms > 100:  # Only show when there's actual audio
                    print(f"RMS Volume: {rms:.0f}")
                    
                time.sleep(0.1)
                
            except Exception as e:
                print(f"Error reading stream: {e}")
                break
                
    except KeyboardInterrupt:
        print("\nStopped.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        try:
            stream.stop_stream()
            stream.close()
        except:
            pass
        p.terminate()

if __name__ == "__main__":
    capture_with_wasapi_loopback()